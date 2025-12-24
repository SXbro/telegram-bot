import os
import base64
import logging
import threading
from datetime import datetime
from flask import Flask  # <-- ADDED for Render
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv
from db import init_db, add_user, add_message, get_user_stats, get_all_users, user_exists

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# IMPORTANT: Update these with your actual information
ADMIN_ID = 1868394048  # Replace with YOUR Telegram user ID
BOT_USERNAME = "anonymonbot"  # Replace with YOUR bot's username (without @)

# Validate configuration
if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env file!")
    exit(1)

# --- Your existing bot functions below (unchanged) ---

def encode_user_id(user_id):
    try:
        user_str = str(user_id)
        encoded_bytes = base64.urlsafe_b64encode(user_str.encode('utf-8'))
        encoded_str = encoded_bytes.decode('utf-8')
        logger.info(f"Encoded user_id {user_id} -> {encoded_str}")
        return encoded_str
    except Exception as e:
        logger.error(f"Error encoding user ID {user_id}: {e}")
        return None

def decode_user_id(encoded_id):
    try:
        decoded_bytes = base64.urlsafe_b64decode(encoded_id.encode('utf-8'))
        decoded_str = decoded_bytes.decode('utf-8')
        user_id = int(decoded_str)
        logger.info(f"Decoded {encoded_id} -> user_id {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"Error decoding user ID '{encoded_id}': {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        add_user(user.id, user.username, user.first_name)
        logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        if context.args and len(context.args) > 0:
            encoded_target_id = context.args[0]
            logger.info(f"Processing anonymous link with parameter: {encoded_target_id}")
            target_user_id = decode_user_id(encoded_target_id)
            
            if target_user_id is None:
                await update.message.reply_text("❌ Invalid link format.")
                return
            
            if user_exists(target_user_id):
                context.user_data['target_user_id'] = target_user_id
                context.user_data['is_anonymous'] = True
                await update.message.reply_text(
                    "💬 Send me a text message and I'll deliver it anonymously!\n\n"
                    "⚠️ Only text messages are allowed."
                )
            else:
                logger.warning(f"Target user {target_user_id} NOT found in database")
                await update.message.reply_text(
                    "👤 The user is not active yet.\n\n"
                    "Please ask them to open the bot first by sending /start"
                )
        else:
            encoded_id = encode_user_id(user.id)
            if encoded_id is None:
                await update.message.reply_text("❌ Error generating your link. Please try again.")
                return
            anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
            keyboard = [
                [InlineKeyboardButton("📤 Share on Telegram", url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message!")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"👋 Hi {user.first_name}!\n\n"
                f"🔗 Your anonymous message link:\n"
                f"`{anonymous_link}`\n\n"
                f"Share this link and people can send you anonymous messages!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            print(f"🔗 Generated link for user {user.id}: {anonymous_link}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        message_text = update.message.text
        
        if context.user_data.get('is_anonymous'):
            target_user_id = context.user_data.get('target_user_id')
            if target_user_id:
                add_message(user.id, target_user_id, message_text)
                logger.info(f"Anonymous message sent from {user.id} to {target_user_id}")
                keyboard = [[InlineKeyboardButton("💬 Reply Anonymously", callback_data=f"reply_{user.id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                try:
                    await context.bot.send_message(chat_id=target_user_id, text=f"📩 Anonymous message:\n\n{message_text}", reply_markup=reply_markup)
                    await update.message.reply_text("✅ Message sent anonymously!")
                    context.user_data.clear()
                except Exception as e:
                    logger.error(f"Failed to send message to {target_user_id}: {e}")
                    await update.message.reply_text("❌ Failed to send message. User might have blocked the bot.")
                    context.user_data.clear()
        
        elif context.user_data.get('replying_to'):
            reply_to_user_id = context.user_data.get('replying_to')
            try:
                await context.bot.send_message(
                    chat_id=reply_to_user_id,
                    text=f"💭 Anonymous reply:\n\n{message_text}\n\n💡 You're chatting anonymously. They won't see who you are."
                )
                await update.message.reply_text("✅ Reply sent!")
                context.user_data.clear()
                logger.info(f"Reply sent from {user.id} to {reply_to_user_id}")
            except Exception as e:
                logger.error(f"Failed to send reply to {reply_to_user_id}: {e}")
                await update.message.reply_text("❌ Failed to send reply.")
                context.user_data.clear()
        
        else:
            encoded_id = encode_user_id(user.id)
            if encoded_id:
                anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
                await update.message.reply_text(
                    f"💡 Your anonymous link:\n`{anonymous_link}`\n\nShare this link to receive anonymous messages!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Error generating your link. Please try /start again.")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("reply_"):
            anonymous_user_id = int(data.replace("reply_", ""))
            context.user_data['replying_to'] = anonymous_user_id
            await query.edit_message_text(f"{query.message.text}\n\n💬 Send me your reply and I'll deliver it anonymously!")
    except Exception as e:
        logger.error(f"Error handling callback: {e}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        if not context.args:
            await update.message.reply_text("📢 Usage: /broadcast <message>")
            return
        message = " ".join(context.args)
        users = get_all_users()
        if not users:
            await update.message.reply_text("❌ No users found in database.")
            return
        sent_count = 0
        failed_count = 0
        status_msg = await update.message.reply_text(f"📤 Broadcasting to {len(users)} users...")
        for user_id, username, first_name in users:
            if user_id == ADMIN_ID:
                continue
            try:
                await context.bot.send_message(chat_id=user_id, text=f"📢 Broadcast Message:\n\n{message}")
                sent_count += 1
                logger.info(f"Broadcast sent to user {user_id}")
            except Exception as e:
                failed_count += 1
                logger.warning(f"Failed to send broadcast to {user_id}: {e}")
        await status_msg.edit_text(
            f"✅ Broadcast complete!\n\n📤 Sent: {sent_count}\n❌ Failed: {failed_count}\n📊 Total users: {len(users)}"
        )
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        await update.message.reply_text("❌ An error occurred during broadcast.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        user_count, message_count = get_user_stats()
        await update.message.reply_text(
            f"📊 Bot Statistics:\n\n👥 Total users: {user_count}\n💬 Anonymous messages: {message_count}"
        )
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching stats.")

async def debug_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        users = get_all_users()
        if not users:
            await update.message.reply_text("❌ No users found in database.")
            return
        user_list = []
        for user_id, username, first_name in users[:10]:
            user_list.append(f"• {user_id} - {first_name} (@{username})")
        await update.message.reply_text(
            f"🔍 Users in database (showing first 10):\n\n" + 
            "\n".join(user_list) +
            f"\n\n📊 Total: {len(users)} users"
        )
    except Exception as e:
        logger.error(f"Error in debug_users command: {e}")

# --- NEW: Bot runner function (for background thread) ---
def run_bot():
    """Run the Telegram bot in polling mode."""
    try:
        init_db()
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("debug", debug_users))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(handle_callback))
        logger.info("🤖 Telegram bot started in background thread.")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")

# --- NEW: Flask app for Render ---
app = Flask(__name__)

@app.route("/")
def health_check():
    """Health check endpoint for Render."""
    return "✅ Bot is running!", 200

# --- Start bot in background when this file runs ---
if __name__ == "__main__":
    # Start Telegram bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Start Flask app (Render will bind to $PORT)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
