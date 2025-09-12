import logging
import os
import time
import hashlib
from typing import Dict

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

from db import DatabaseHandler

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
OWNER_ID = 1868394048  # 👈 Replace this with your actual Telegram user ID

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AnonymousMessageBot:
    def __init__(self, bot_token: str, bot_username: str):
        self.bot_token = bot_token
        self.bot_username = bot_username
        self.db = DatabaseHandler()
        self.user_states: Dict[int, str] = {}
        self.pending_messages: Dict[int, int] = {}

    def generate_stable_user_link(self, user_id: int) -> str:
        """Generate stable invite link (same per user)"""
        user_hash = hashlib.md5(str(user_id).encode()).hexdigest()[:10]
        return f"https://t.me/{self.bot_username}?start={user_id}_{user_hash}"

    def extract_user_id_from_start(self, start_param: str) -> int:
        try:
            return int(start_param.split('_')[0])
        except (ValueError, IndexError):
            return None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id

        # Save user to database
        self.db.add_user(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Handle if user clicked a referral link
        if context.args:
            receiver_id = self.extract_user_id_from_start(context.args[0])
            if receiver_id and receiver_id != user_id:
                receiver_info = self.db.get_user(receiver_id)
                if receiver_info:
                    self.user_states[user_id] = "sending_message"
                    self.pending_messages[user_id] = receiver_id

                    await update.message.reply_text(
                        "🔗 You've been invited to send an anonymous message!\n\n"
                        "📝 Please type your message below (text only):\n\n"
                        "⚠️ Note: Your message will be sent anonymously."
                    )
                    return
                else:
                    await update.message.reply_text(
                        "❌ Invalid link. The user might not exist or hasn't used the bot yet."
                    )
                    return
            else:
                await update.message.reply_text(
                    "❌ Invalid link or you can't send a message to yourself."
                )
                return

        # Default user start - show invite link
        invite_link = self.generate_stable_user_link(user_id)

        welcome_message = (
            f"🎭 Welcome to Anonymous Message Bot!\n\n"
            f"👤 Your unique link:\n"
            f"`{invite_link}`\n\n"
            f"📤 **How to use:**\n"
            f"1. Share your link with others\n"
            f"2. They can send you anonymous messages\n"
            f"3. You'll receive them here\n\n"
            f"🔒 All messages are anonymous!"
        )

        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

    async def newlink_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != OWNER_ID:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return

        new_link = self.generate_stable_user_link(user_id)
        await update.message.reply_text(
            f"🔗 Your new anonymous message link:\n"
            f"`{new_link}`",
            parse_mode=ParseMode.MARKDOWN
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != OWNER_ID:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return

        stats = self.db.get_stats()
        stats_message = (
            f"📊 **Bot Statistics:**\n\n"
            f"👥 Total users: {stats['total_users']}\n"
            f"💬 Total messages: {stats['total_messages']}"
        )
        await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != OWNER_ID:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return

        if not context.args:
            await update.message.reply_text("⚠️ Usage: /broadcast Your message here.")
            return

        msg_text = "📢 *Broadcast Message:*\n\n" + " ".join(context.args)
        users = self.db.get_all_user_ids()  # Must return list of user IDs

        sent, failed = 0, 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=msg_text, parse_mode=ParseMode.MARKDOWN)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {uid}: {e}")
                failed += 1

        await update.message.reply_text(
            f"✅ Broadcast sent!\n📬 Delivered: {sent} | ❌ Failed: {failed}"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text

        if user_id in self.user_states and self.user_states[user_id] == "sending_message":
            receiver_id = self.pending_messages.get(user_id)
            if receiver_id:
                if self.db.save_message(user_id, receiver_id, message_text):
                    try:
                        await context.bot.send_message(
                            chat_id=receiver_id,
                            text=f"📨 **Anonymous Message:**\n\n{message_text}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await update.message.reply_text("✅ Message sent anonymously.")
                    except Exception as e:
                        logger.error(f"Failed to send to {receiver_id}: {e}")
                        await update.message.reply_text("❌ Could not deliver the message.")
                else:
                    await update.message.reply_text("❌ Failed to save your message.")

                del self.user_states[user_id]
                del self.pending_messages[user_id]
            else:
                await update.message.reply_text("❌ Something went wrong. Try using the link again.")
        else:
            await update.message.reply_text(
                "🤔 You need to use someone's invite link to send an anonymous message.\n"
                "💡 Use /start to get your own link!"
            )

    async def handle_non_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Only plain text messages are supported.")

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ This command does not exist.")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Exception while handling update: {context.error}")

    def run(self):
        app = Application.builder().token(self.bot_token).build()

        # Public commands
        app.add_handler(CommandHandler("start", self.start_command))

        # Admin-only commands
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CommandHandler("newlink", self.newlink_command))
        app.add_handler(CommandHandler("broadcast", self.broadcast_command))

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, self.handle_non_text))

        # Unknown command handler (must be last)
        app.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))

        app.add_error_handler(self.error_handler)

        logger.info("🚀 Bot started and running...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    if not BOT_TOKEN or not BOT_USERNAME:
        print("❌ BOT_TOKEN or BOT_USERNAME not set in environment.")
        return

    bot = AnonymousMessageBot(BOT_TOKEN, BOT_USERNAME)
    bot.run()

if __name__ == "__main__":
    main()