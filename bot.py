import os
import base64
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
from config import *
from db import (
    init_db, migrate_existing_data, add_user, add_message, get_user_stats, 
    get_all_users, user_exists, update_user_activity, get_user_profile,
    get_message_history, block_user, unblock_user, is_blocked,
    is_user_blocked_by_admin, block_user_by_admin, unblock_user_by_admin,
    get_admin_analytics, get_user_settings, update_user_settings,
    get_rate_limit_count, report_message, get_connection
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def encode_user_id(user_id):
    """Encode user ID for the anonymous link using base64"""
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
    """Decode user ID from the anonymous link"""
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
    """Handle /start command with enhanced onboarding"""
    try:
        user = update.effective_user
        
        # Check if user is blocked by admin
        if is_user_blocked_by_admin(user.id):
            await update.message.reply_text(
                "🚫 Your account has been blocked.\n\n"
                "If you believe this is a mistake, please contact support."
            )
            return
        
        # Add user to database with enhanced fields
        add_user(
            user.id, 
            user.username, 
            user.first_name,
            user.last_name,
            user.language_code,
            user.is_bot,
            user.is_premium if hasattr(user, 'is_premium') else False
        )
        update_user_activity(user.id)
        logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        # Check if this is an anonymous message start
        if context.args and len(context.args) > 0:
            encoded_target_id = context.args[0]
            logger.info(f"Processing anonymous link with parameter: {encoded_target_id}")
            
            # Decode the target user ID
            target_user_id = decode_user_id(encoded_target_id)
            
            if target_user_id is None:
                logger.warning(f"Failed to decode user ID from: {encoded_target_id}")
                await update.message.reply_text("❌ Invalid link format.")
                return
            
            # Check if sender is blocked by target
            if is_blocked(target_user_id, user.id):
                await update.message.reply_text(
                    "🚫 You cannot send messages to this user.\n\n"
                    "You may have been blocked."
                )
                return
            
            # Check if target user exists in database
            if user_exists(target_user_id):
                logger.info(f"Target user {target_user_id} found in database - allowing anonymous message")
                
                # Store the target user ID for this session
                context.user_data['target_user_id'] = target_user_id
                context.user_data['is_anonymous'] = True
                
                # Get target user settings
                settings = get_user_settings(target_user_id)
                
                media_text = ""
                if settings.get('allow_media') and ENABLE_MEDIA_MESSAGES:
                    media_text = "\n📷 You can also send photos!"
                
                await update.message.reply_text(
                    "💬 **Send Anonymous Message**\n\n"
                    f"Type your message and I'll deliver it anonymously!{media_text}\n\n"
                    "⚠️ Be respectful - spam and abuse will be reported.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                logger.warning(f"Target user {target_user_id} NOT found in database")
                await update.message.reply_text(
                    "👤 **User Not Active**\n\n"
                    "This user hasn't started the bot yet.\n"
                    "Please ask them to open @" + BOT_USERNAME + " first!"
                )
        else:
            # Regular start - show enhanced welcome message
            encoded_id = encode_user_id(user.id)
            
            if encoded_id is None:
                await update.message.reply_text("❌ Error generating your link. Please try again.")
                return
                
            anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
            
            # Create buttons
            keyboard = [
                [InlineKeyboardButton("📤 Share Your Link", url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message! 💬")],
                [InlineKeyboardButton("📊 View Profile", callback_data="view_profile"),
                 InlineKeyboardButton("❓ Help", callback_data="show_help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_msg = (
                f"👋 **Welcome, {user.first_name}!**\n\n"
                f"🎭 Receive anonymous messages with this bot!\n\n"
                f"🔗 **Your Anonymous Link:**\n"
                f"`{anonymous_link}`\n\n"
                f"📤 Share this link and people can send you anonymous messages!\n\n"
                f"💡 **Quick Commands:**\n"
                f"• /profile - View your statistics\n"
                f"• /history - See recent messages\n"
                f"• /help - Get help and tips"
            )
            
            await update.message.reply_text(
                welcome_msg,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Generated link for user {user.id}: {anonymous_link}")
            
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try /start again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive help information"""
    try:
        help_text = (
            "❓ **How to Use Anonymous Message Bot**\n\n"
            "**📥 Receiving Messages:**\n"
            "1. Share your anonymous link with others\n"
            "2. They click the link and send you messages\n"
            "3. You receive messages anonymously!\n\n"
            "**📤 Sending Messages:**\n"
            "1. Click someone's anonymous link\n"
            "2. Type your message\n"
            "3. It's delivered anonymously!\n\n"
            "**🛡️ Safety Features:**\n"
            "• Block users who spam you\n"
            "• Report inappropriate messages\n"
            "• Rate limiting prevents spam\n\n"
            "**📋 Available Commands:**\n"
            "• /start - Get your anonymous link\n"
            "• /profile - View your statistics\n"
            "• /history - See recent messages\n"
            "• /settings - Manage preferences\n"
            "• /help - Show this help message\n\n"
            "**💡 Tips:**\n"
            "• Be respectful and kind\n"
            "• Don't share personal information\n"
            "• Report spam or abuse\n\n"
            "Need more help? Contact @" + BOT_USERNAME
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Start", callback_data="back_to_start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await update.message.reply_text("❌ Error showing help.")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile and statistics"""
    try:
        user = update.effective_user
        update_user_activity(user.id)
        
        profile = get_user_profile(user.id)
        
        if not profile:
            await update.message.reply_text("❌ Profile not found. Please use /start first.")
            return
        
        # Format dates
        join_date = datetime.fromisoformat(profile['join_date']).strftime('%B %d, %Y')
        
        # Generate link
        encoded_id = encode_user_id(user.id)
        anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
        
        premium_badge = " ⭐" if profile.get('is_premium') else ""
        
        profile_text = (
            f"👤 **Your Profile**{premium_badge}\n\n"
            f"**Name:** {profile['first_name']}\n"
            f"**Username:** @{profile['username'] or 'Not set'}\n"
            f"**Member since:** {join_date}\n\n"
            f"📊 **Statistics:**\n"
            f"• Messages sent: {profile['messages_sent']}\n"
            f"• Messages received: {profile['messages_received']}\n\n"
            f"🔗 **Your Link:**\n"
            f"`{anonymous_link}`"
        )
        
        keyboard = [
            [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message! 💬")],
            [InlineKeyboardButton("📜 View History", callback_data="view_history"),
             InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            profile_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await update.message.reply_text("❌ Error loading profile.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show message history"""
    try:
        user = update.effective_user
        update_user_activity(user.id)
        
        messages = get_message_history(user.id, limit=10)
        
        if not messages:
            await update.message.reply_text(
                "📭 **No Messages Yet**\n\n"
                "You haven't sent or received any messages yet.\n"
                "Share your link to start receiving anonymous messages!"
            )
            return
        
        history_text = "📜 **Recent Messages** (Last 10)\n\n"
        
        for msg in messages:
            timestamp = datetime.fromisoformat(msg['timestamp']).strftime('%b %d, %H:%M')
            direction = "📤 Sent" if msg['direction'] == 'sent' else "📥 Received"
            content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
            read_status = "✓" if msg['is_read'] else "○"
            
            history_text += f"{direction} {read_status} - {timestamp}\n_{content_preview}_\n\n"
        
        await update.message.reply_text(
            history_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in history command: {e}")
        await update.message.reply_text("❌ Error loading history.")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user settings"""
    try:
        user = update.effective_user
        settings = get_user_settings(user.id)
        
        keyboard = [
            [InlineKeyboardButton(
                f"🔔 Notifications: {'ON' if settings['notifications_enabled'] else 'OFF'}",
                callback_data="toggle_notifications"
            )],
            [InlineKeyboardButton(
                f"📷 Allow Media: {'ON' if settings['allow_media'] else 'OFF'}",
                callback_data="toggle_media"
            )],
            [InlineKeyboardButton(
                f"👁️ Read Receipts: {'ON' if settings['show_read_receipts'] else 'OFF'}",
                callback_data="toggle_read_receipts"
            )],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚙️ **Settings**\n\n"
            "Customize your anonymous messaging experience:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in settings command: {e}")
        await update.message.reply_text("❌ Error loading settings.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages with spam protection"""
    try:
        user = update.effective_user
        message_text = update.message.text
        
        # Check if user is blocked
        if is_user_blocked_by_admin(user.id):
            await update.message.reply_text("🚫 Your account has been blocked.")
            return
        
        update_user_activity(user.id)
        
        # Check if user is in anonymous mode
        if context.user_data.get('is_anonymous'):
            target_user_id = context.user_data.get('target_user_id')
            
            if target_user_id:
                # Spam protection
                if ENABLE_SPAM_PROTECTION:
                    msg_count = get_rate_limit_count(user.id, hours=1)
                    if msg_count >= MAX_MESSAGES_PER_HOUR:
                        await update.message.reply_text(
                            "⏰ **Rate Limit Exceeded**\n\n"
                            f"You can send maximum {MAX_MESSAGES_PER_HOUR} messages per hour.\n"
                            "Please try again later."
                        )
                        context.user_data.clear()
                        return
                
                # Send anonymous message
                add_message(user.id, target_user_id, message_text, 'text')
                logger.info(f"Anonymous message sent from {user.id} to {target_user_id}")
                
                # Get the message ID that was just created
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM messages ORDER BY id DESC LIMIT 1')
                result = cursor.fetchone()
                message_id = result[0] if result else 0
                conn.close()
                
                # Create action buttons for the recipient with message_id
                keyboard = [
                    [InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user.id}_{message_id}"),
                     InlineKeyboardButton("🚫 Block", callback_data=f"block_{user.id}")],
                    [InlineKeyboardButton("⭐ Rate Message", callback_data=f"rate_{user.id}_{message_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send message to target user
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📩 **Anonymous Message:**\n\n{message_text}",
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Confirm to sender
                    await update.message.reply_text(
                        "✅ **Message Sent!**\n\n"
                        "Your anonymous message has been delivered successfully! 🎉"
                    )
                    
                    # Clear anonymous mode
                    context.user_data.clear()
                    
                except Exception as e:
                    logger.error(f"Failed to send message to {target_user_id}: {e}")
                    await update.message.reply_text(
                        "❌ **Delivery Failed**\n\n"
                        "The user might have blocked the bot or deleted their account."
                    )
                    context.user_data.clear()
        
        elif context.user_data.get('replying_to'):
            # Handle reply to anonymous message
            reply_to_user_id = context.user_data.get('replying_to')
            
            # Spam protection for replies
            if ENABLE_SPAM_PROTECTION:
                msg_count = get_rate_limit_count(user.id, hours=1)
                if msg_count >= MAX_MESSAGES_PER_HOUR:
                    await update.message.reply_text(
                        "⏰ Rate limit exceeded. Please try again later."
                    )
                    context.user_data.clear()
                    return
            
            # Send reply back to anonymous user
            try:
                add_message(user.id, reply_to_user_id, message_text, 'text')
                
                # Add reply button so conversation can continue
                keyboard = [
                    [InlineKeyboardButton("💬 Reply Back", callback_data=f"reply_{user.id}_0")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=reply_to_user_id,
                    text=f"💭 **Anonymous Reply:**\n\n{message_text}\n\n"
                         f"💡 _You're chatting anonymously. They don't know who you are._",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                await update.message.reply_text("✅ **Reply Sent!**")
                context.user_data.clear()
                logger.info(f"Reply sent from {user.id} to {reply_to_user_id}")
                
            except Exception as e:
                logger.error(f"Failed to send reply to {reply_to_user_id}: {e}")
                await update.message.reply_text("❌ Failed to send reply.")
                context.user_data.clear()
        
        else:
            # Regular message - show their link again
            encoded_id = encode_user_id(user.id)
            if encoded_id:
                anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
                
                keyboard = [
                    [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message! 💬")],
                    [InlineKeyboardButton("📊 Profile", callback_data="view_profile"),
                     InlineKeyboardButton("❓ Help", callback_data="show_help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"💡 **Your Anonymous Link:**\n`{anonymous_link}`\n\n"
                    f"Share this link to receive anonymous messages!",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text("❌ Error generating your link. Please try /start again.")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages"""
    try:
        if not ENABLE_MEDIA_MESSAGES:
            await update.message.reply_text("📷 Photo messages are currently disabled.")
            return
        
        user = update.effective_user
        
        if context.user_data.get('is_anonymous'):
            target_user_id = context.user_data.get('target_user_id')
            
            if target_user_id:
                # Check if target allows media
                settings = get_user_settings(target_user_id)
                if not settings.get('allow_media'):
                    await update.message.reply_text(
                        "📷 This user doesn't accept photo messages.\n"
                        "Please send a text message instead."
                    )
                    return
                
                # Get caption if any
                caption = update.message.caption or ""
                
                # Save to database
                add_message(user.id, target_user_id, f"[Photo] {caption}", 'photo')
                
                # Forward photo
                try:
                    keyboard = [
                        [InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user.id}_0"),
                         InlineKeyboardButton("🚫 Block", callback_data=f"block_{user.id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_photo(
                        chat_id=target_user_id,
                        photo=update.message.photo[-1].file_id,
                        caption=f"📩 **Anonymous Photo**\n\n{caption}",
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    await update.message.reply_text("✅ Photo sent anonymously!")
                    context.user_data.clear()
                    
                except Exception as e:
                    logger.error(f"Failed to send photo: {e}")
                    await update.message.reply_text("❌ Failed to send photo.")
                    context.user_data.clear()
        else:
            await update.message.reply_text(
                "📷 To send photos anonymously, click someone's anonymous link first!"
            )
            
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await update.message.reply_text("❌ Error processing photo.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if data.startswith("reply_"):
            # Extract user_id and message_id from callback data
            parts = data.replace("reply_", "").split("_")
            anonymous_user_id = int(parts[0])
            context.user_data['replying_to'] = anonymous_user_id
            
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"💬 **Reply Mode Active**\n"
                f"Send your reply and I'll deliver it anonymously!",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data.startswith("block_"):
            anonymous_user_id = int(data.replace("block_", ""))
            block_user(user.id, anonymous_user_id)
            
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"🚫 **User Blocked**\n"
                f"This user can no longer send you messages.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"User {user.id} blocked {anonymous_user_id}")
        
        elif data.startswith("rate_"):
            # Extract user_id and message_id
            parts = data.replace("rate_", "").split("_")
            anonymous_user_id = int(parts[0])
            message_id = int(parts[1]) if len(parts) > 1 else 0
            
            keyboard = [
                [InlineKeyboardButton("⭐", callback_data=f"rating_1_{anonymous_user_id}_{message_id}"),
                 InlineKeyboardButton("⭐⭐", callback_data=f"rating_2_{anonymous_user_id}_{message_id}"),
                 InlineKeyboardButton("⭐⭐⭐", callback_data=f"rating_3_{anonymous_user_id}_{message_id}")],
                [InlineKeyboardButton("🚨 Report", callback_data=f"report_{anonymous_user_id}_{message_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        
        elif data.startswith("rating_"):
            parts = data.split("_")
            rating = int(parts[1])
            message_id = int(parts[3]) if len(parts) > 3 else 0
            
            # Save rating to database
            if message_id > 0:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE messages SET rating = ? WHERE id = ?', (rating, message_id))
                    conn.commit()
                    conn.close()
                    logger.info(f"Message {message_id} rated {rating} stars")
                except Exception as e:
                    logger.error(f"Error saving rating: {e}")
            
            await query.answer(f"Rated {rating} stars! ⭐")
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"⭐ Rated: {'⭐' * rating}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data.startswith("report_"):
            parts = data.replace("report_", "").split("_")
            reported_user_id = int(parts[0])
            message_id = int(parts[1]) if len(parts) > 1 else 0
            
            # Save report to database
            if message_id > 0:
                try:
                    report_message(user.id, message_id, reported_user_id, "User reported via button")
                    logger.info(f"Message {message_id} reported by {user.id}")
                except Exception as e:
                    logger.error(f"Error saving report: {e}")
            
            await query.answer("Message reported to admin")
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"🚨 **Reported**\n"
                f"Thank you for keeping our community safe.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "view_profile":
            # Create a fake update object for compatibility
            profile = get_user_profile(user.id)
            if not profile:
                await query.answer("Profile not found")
                return
            
            encoded_id = encode_user_id(user.id)
            anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
            
            profile_text = (
                f"👤 **Your Profile**\n\n"
                f"**Name:** {profile['first_name']}\n"
                f"**Username:** @{profile['username'] or 'Not set'}\n\n"
                f"📊 **Statistics:**\n"
                f"• Messages sent: {profile['messages_sent']}\n"
                f"• Messages received: {profile['messages_received']}\n\n"
                f"🔗 **Your Link:**\n"
                f"`{anonymous_link}`"
            )
            
            await query.edit_message_text(profile_text, parse_mode=ParseMode.MARKDOWN)
        
        elif data == "view_history":
            messages = get_message_history(user.id, limit=10)
            
            if not messages:
                await query.answer("No messages yet")
                return
            
            history_text = "📜 **Recent Messages** (Last 10)\n\n"
            for msg in messages:
                timestamp = datetime.fromisoformat(msg['timestamp']).strftime('%b %d, %H:%M')
                direction = "📤 Sent" if msg['direction'] == 'sent' else "📥 Received"
                content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
                history_text += f"{direction} - {timestamp}\n_{content_preview}_\n\n"
            
            await query.edit_message_text(history_text, parse_mode=ParseMode.MARKDOWN)
        
        elif data == "show_help":
            help_text = (
                "❓ **How to Use Anonymous Message Bot**\n\n"
                "**📥 Receiving Messages:**\n"
                "1. Share your anonymous link\n"
                "2. Receive anonymous messages\n\n"
                "**📤 Sending Messages:**\n"
                "1. Click someone's link\n"
                "2. Type your message\n\n"
                "Use /start to get your link!"
            )
            await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
        
        elif data == "show_settings":
            settings = get_user_settings(user.id)
            
            keyboard = [
                [InlineKeyboardButton(
                    f"🔔 Notifications: {'ON' if settings['notifications_enabled'] else 'OFF'}",
                    callback_data="toggle_notifications"
                )],
                [InlineKeyboardButton(
                    f"📷 Allow Media: {'ON' if settings['allow_media'] else 'OFF'}",
                    callback_data="toggle_media"
                )],
                [InlineKeyboardButton(
                    f"👁️ Read Receipts: {'ON' if settings['show_read_receipts'] else 'OFF'}",
                    callback_data="toggle_read_receipts"
                )],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚙️ **Settings**\n\nCustomize your experience:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data.startswith("toggle_"):
            setting = data.replace("toggle_", "")
            settings = get_user_settings(user.id)
            
            if setting == "notifications":
                new_value = not settings['notifications_enabled']
                update_user_settings(user.id, notifications_enabled=new_value)
                await query.answer(f"Notifications {'enabled' if new_value else 'disabled'}")
            elif setting == "media":
                new_value = not settings['allow_media']
                update_user_settings(user.id, allow_media=new_value)
                await query.answer(f"Media messages {'enabled' if new_value else 'disabled'}")
            elif setting == "read_receipts":
                new_value = not settings['show_read_receipts']
                update_user_settings(user.id, show_read_receipts=new_value)
                await query.answer(f"Read receipts {'enabled' if new_value else 'disabled'}")
            
            # Refresh settings display - call show_settings callback
            context.user_data['temp_callback'] = 'show_settings'
            await handle_callback(update, context)
        
        elif data == "back_to_start":
            encoded_id = encode_user_id(user.id)
            anonymous_link = f"https://t.me/{BOT_USERNAME}?start={encoded_id}"
            
            keyboard = [
                [InlineKeyboardButton("📤 Share Your Link", url=f"https://t.me/share/url?url={anonymous_link}&text=Send me an anonymous message! 💬")],
                [InlineKeyboardButton("📊 View Profile", callback_data="view_profile"),
                 InlineKeyboardButton("❓ Help", callback_data="show_help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_msg = (
                f"👋 **Welcome back!**\n\n"
                f"🔗 **Your Anonymous Link:**\n"
                f"`{anonymous_link}`\n\n"
                f"Share this link to receive anonymous messages!"
            )
            
            await query.edit_message_text(welcome_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        logger.error(f"Error handling callback: {e}")

# Admin Commands

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin dashboard with analytics"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        analytics = get_admin_analytics()
        
        dashboard_text = (
            "👨‍💼 **Admin Dashboard**\n\n"
            f"📊 **Overall Statistics:**\n"
            f"• Total users: {analytics['total_users']}\n"
            f"• Total messages: {analytics['total_messages']}\n"
            f"• Active users (7d): {analytics['active_users_7d']}\n"
            f"• New users (24h): {analytics['new_users_24h']}\n"
            f"• Messages today: {analytics['messages_today']}\n\n"
            f"🛡️ **Moderation:**\n"
            f"• Pending reports: {analytics['pending_reports']}\n"
            f"• Blocked users: {analytics['blocked_users']}\n\n"
            f"**Available Commands:**\n"
            f"• /broadcast \u003cmessage\u003e - Send to all users\n"
            f"• /ban \u003cuser_id\u003e - Block a user\n"
            f"• /unban \u003cuser_id\u003e - Unblock a user\n"
            f"• /stats - Quick statistics"
        )
        
        await update.message.reply_text(dashboard_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in admin dashboard: {e}")
        await update.message.reply_text("❌ Error loading dashboard.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast message to all users"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text("📢 Usage: /broadcast \u003cmessage\u003e")
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
                    text=f"📢 **Announcement:**\n\n{message}",
                    parse_mode=ParseMode.MARKDOWN
                )
                sent_count += 1
                logger.info(f"Broadcast sent to user {user_id}")
                
            except Exception as e:
                failed_count += 1
                logger.warning(f"Failed to send broadcast to {user_id}: {e}")
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete!**\n\n"
            f"📤 Sent: {sent_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"📊 Total users: {len(users)}",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        await update.message.reply_text("❌ An error occurred during broadcast.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to ban a user"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /ban \u003cuser_id\u003e [reason]")
            return
        
        user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Violation of terms"
        
        block_user_by_admin(user_id, reason)
        
        await update.message.reply_text(f"✅ User {user_id} has been banned.\nReason: {reason}")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error in ban command: {e}")
        await update.message.reply_text("❌ Error banning user.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to unban a user"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /unban \u003cuser_id\u003e")
            return
        
        user_id = int(context.args[0])
        unblock_user_by_admin(user_id)
        
        await update.message.reply_text(f"✅ User {user_id} has been unbanned.")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error in unban command: {e}")
        await update.message.reply_text("❌ Error unbanning user.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get bot statistics"""
    try:
        if update.effective_user.id != ADMIN_ID:
            # Show user their personal stats
            profile = get_user_profile(update.effective_user.id)
            if profile:
                await update.message.reply_text(
                    f"📊 **Your Statistics:**\n\n"
                    f"• Messages sent: {profile['messages_sent']}\n"
                    f"• Messages received: {profile['messages_received']}",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        user_count, message_count = get_user_stats()
        
        await update.message.reply_text(
            f"📊 **Bot Statistics:**\n\n"
            f"👥 Total users: {user_count}\n"
            f"💬 Anonymous messages: {message_count}",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching stats.")

def main():
    """Main function to run the bot"""
    try:
        # Initialize database
        print("🔧 Initializing database...")
        init_db()
        migrate_existing_data()
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("history", history_command))
        application.add_handler(CommandHandler("settings", settings_command))
        
        # Admin commands
        application.add_handler(CommandHandler("admin", admin_dashboard))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CommandHandler("ban", ban_user))
        application.add_handler(CommandHandler("unban", unban_user))
        application.add_handler(CommandHandler("stats", stats))
        
        # Message handlers
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Callback handler
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Start the bot
        print("=" * 50)
        print("🤖 Anonymous Message Bot Starting...")
        print("=" * 50)
        print(f"📱 Bot username: @{BOT_USERNAME}")
        print(f"👤 Admin ID: {ADMIN_ID}")
        print(f"✅ All features enabled!")
        print(f"📝 Logging to: {LOG_FILE}")
        print("=" * 50)
        print("✅ Bot is running! Press Ctrl+C to stop")
        print("=" * 50)
        
        application.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        print(f"❌ Critical error: {e}")

if __name__ == "__main__":
    main()
