import os
import base64
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import asyncio
from dotenv import load_dotenv
from database import init_db, add_user, add_message, get_user_stats, get_all_users, user_exists

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1868394048'))
BOT_USERNAME = os.getenv('BOT_USERNAME', 'anonymonbot')

# Validate configuration
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables!")
    raise ValueError("BOT_TOKEN is required")

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for Render"""
    return "✅ Bot is running!", 200

@app.route('/health')
def health():
    """Alternative health check endpoint"""
    return {"status": "healthy", "bot": "anonymous_message_bot"}, 200


def encode_user_id(user_id):
    """Encode user ID for anonymous link using base64"""
    try:
        user_str = str(user_id)
        encoded_bytes = base64.urlsafe_b64encode(user_str.encode('utf-8'))
        encoded_str = encoded_bytes.decode('utf-8')
        logger.debug(f"Encoded user_id {user_id} -> {encoded_str}")
        return encoded_str
    except Exception as e:
        logger.error(f"Error encoding user ID {user_id}: {e}")
        return None


def decode_user_id(encoded_id):
    """Decode user ID from anonymous link"""
    try:
        decoded_bytes = base64.urlsafe_b64decode(encoded_id.encode('utf-8'))
        decoded_str = decoded_bytes.decode('utf-8')
        user_id = int(decoded_str)
        logger.debug(f"Decoded {encoded_id} -> user_id {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"Error decoding user ID '{encoded_id}': {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        
        # Add user to database
        add_user(user.id, user.username, user.first_name)
        logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        # Check if this is an anonymous message link
        if context.args and len(context.args) > 0:
            encoded_target_id = context.args[0]
            logger.info(f"Processing anonymous link: {encoded_target_id}")
            
            # Decode target user ID
            target_user_id = decode_user_id(encoded_target_id)
            
            if target_user_id is None:
                logger.warning(f"Failed to decode user ID: {encoded_target_id}")
                await update.message.reply_text("❌ Invalid link format.")
                return
            
            # Check if target user exists
            if user_exists(target_user_id):
                logger.info(f"Target user {target_user_id} found - enabling anonymous mode")
                
                # Store target for this session
                context.user_data['target_user_id'] = target_user_id
                context.user_data['is_anonymous'] = True
                
                await update.message.reply_text(
                    "💬 Send me a text message and I'll deliver it anonymously!\n\n"
                    "⚠️ Only text messages are allowed."
                )
            else:
                logger.warning(f"Target user {target_user_id} not found in database")
                await update.message.reply_text(
                    "👤 The user is not active yet.\n\n"
                    "Please ask them to open the bot first by sending /start"
                )
        else:
            # Regular start - show user's anonymous link
            encoded_id = encode_user_id(user.id)
            
            if encoded_id is None:
                await update.message.reply_text("❌ Error generating your link. Please try again.")
                return
            
            # FIXED: No spaces in URL
            anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
            
            # Share button
            keyboard = [
                [InlineKeyboardButton(
                    "📤 Share on Telegram", 
                    url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message!"
                )]
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
            
            logger.debug(f"Generated link for user {user.id}: {anonymous_link}")
            
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred. Please try again.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages"""
    try:
        user = update.effective_user
        message_text = update.message.text
        
        # Check for /stop command to exit anonymous conversation
        if message_text.lower() in ['/stop', '/exit', '/end']:
            if context.user_data.get('is_anonymous') or context.user_data.get('replying_to'):
                context.user_data.clear()
                await update.message.reply_text(
                    "👋 Anonymous conversation ended.\n\n"
                    "Send /start to get your anonymous link!"
                )
                return
        
        # Check if user is in anonymous mode
        if context.user_data.get('is_anonymous'):
            target_user_id = context.user_data.get('target_user_id')
            
            if target_user_id:
                # Save message to database
                add_message(user.id, target_user_id, message_text)
                logger.info(f"Anonymous message: {user.id} -> {target_user_id}")
                
                # Reply button for recipient (compact text)
                keyboard = [
                    [InlineKeyboardButton("Reply", callback_data=f"reply_{user.id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send message to target user with Reply button
                try:
                    # Add Reply button for continuous conversation
                    keyboard = [
                        [InlineKeyboardButton("Reply", callback_data=f"reply_{user.id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📩 Anonymous message:\n\n{message_text}",
                        reply_markup=reply_markup
                    )
                    
                    # Confirm to sender with tip about continuous messaging
                    await update.message.reply_text(
                        "✅ Message sent anonymously!\n\n"
                        "💡 Send more messages to continue chatting.\n"
                        "Type /stop to end the conversation."
                    )
                    
                    # DON'T clear anonymous mode - keep the conversation going!
                    # context.user_data.clear()
                    
                except Exception as e:
                    logger.error(f"Failed to send to {target_user_id}: {e}")
                    await update.message.reply_text("❌ Failed to send message. User might have blocked the bot.")
                    context.user_data.clear()
        
        elif context.user_data.get('replying_to'):
            # Handle reply to anonymous message
            reply_to_user_id = context.user_data.get('replying_to')
            
            try:
                # Add Reply button to the anonymous reply too
                keyboard = [
                    [InlineKeyboardButton("Reply", callback_data=f"reply_{user.id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=reply_to_user_id,
                    text=f"💭 Anonymous reply:\n\n{message_text}",
                    reply_markup=reply_markup
                )
                
                await update.message.reply_text(
                    "✅ Reply sent!\n\n"
                    "💡 Send more messages to continue.\n"
                    "Type /stop to end the conversation."
                )
                # DON'T clear user_data - keep the conversation going!
                # context.user_data.clear()
                logger.info(f"Reply sent: {user.id} -> {reply_to_user_id}")
                
            except Exception as e:
                logger.error(f"Failed to send reply to {reply_to_user_id}: {e}")
                await update.message.reply_text("❌ Failed to send reply.")
                context.user_data.clear()
        
        else:
            # Regular message - show link again
            encoded_id = encode_user_id(user.id)
            if encoded_id:
                anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
                
                await update.message.reply_text(
                    f"💡 Your anonymous link:\n`{anonymous_link}`\n\n"
                    f"Share this link to receive anonymous messages!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Error generating your link. Please try /start again.")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred. Please try again.")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("reply_"):
            anonymous_user_id = int(data.replace("reply_", ""))
            context.user_data['replying_to'] = anonymous_user_id
            
            # Send a NEW message instead of editing the original
            # This keeps the Reply button visible for future messages
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="💬 Send me your reply and I'll deliver it anonymously!\n\n"
                     "You can send multiple messages - each one will be delivered."
            )
    
    except Exception as e:
        logger.error(f"Error handling callback: {e}", exc_info=True)


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast message to all users"""
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
            try:
                if user_id == ADMIN_ID:
                    continue
                    
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=f"📢 Broadcast Message:\n\n{message}"
                )
                sent_count += 1
                logger.info(f"Broadcast sent to {user_id}")
                
            except Exception as e:
                failed_count += 1
                logger.warning(f"Failed broadcast to {user_id}: {e}")
        
        await status_msg.edit_text(
            f"✅ Broadcast complete!\n\n"
            f"📤 Sent: {sent_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"📊 Total users: {len(users)}"
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred during broadcast.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get bot statistics"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        user_count, message_count = get_user_stats()
        
        await update.message.reply_text(
            f"📊 Bot Statistics:\n\n"
            f"👥 Total users: {user_count}\n"
            f"💬 Anonymous messages: {message_count}"
        )
        
    except Exception as e:
        logger.error(f"Error in stats: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred while fetching stats.")


async def debug_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to see users in database"""
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
            user_list.append(f"• {user_id} - {first_name} (@{username or 'N/A'})")
        
        await update.message.reply_text(
            f"🔍 Users in database (showing first 10):\n\n" + 
            "\n".join(user_list) +
            f"\n\n📊 Total: {len(users)} users"
        )
        
    except Exception as e:
        logger.error(f"Error in debug_users: {e}", exc_info=True)


async def run_bot_async():
    """Run the Telegram bot in polling mode (async version for v21+)"""
    try:
        # Initialize database
        init_db()
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("debug", debug_users))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Start polling
        logger.info("🤖 Bot starting in polling mode...")
        logger.info(f"📱 Bot username: @{BOT_USERNAME}")
        logger.info(f"👤 Admin ID: {ADMIN_ID}")
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopping...")
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
        
    except Exception as e:
        logger.error(f"Critical error in bot: {e}", exc_info=True)
        raise

def run_bot():
    """Wrapper to run async bot in thread"""
    asyncio.run(run_bot_async())


def start_bot_thread():
    """Start bot in a background thread"""
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Bot thread started")
    return bot_thread


if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = start_bot_thread()
    
    # Get port from environment (Render provides this)
    port = int(os.getenv('PORT', 5000))
    
    # Start Flask app
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
