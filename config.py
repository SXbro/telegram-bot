"""
Configuration management for Anonymous Message Bot
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'anonymonbot')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1868394048'))

# Feature Flags
ENABLE_MEDIA_MESSAGES = True
ENABLE_VOICE_MESSAGES = True
ENABLE_SPAM_PROTECTION = True
ENABLE_READ_RECEIPTS = True
ENABLE_MESSAGE_REACTIONS = True

# Rate Limiting
MAX_MESSAGES_PER_HOUR = 10
MAX_MESSAGES_PER_DAY = 50
SPAM_THRESHOLD = 5  # Messages in 5 minutes

# Message Settings
MAX_MESSAGE_LENGTH = 4096
WELCOME_MESSAGE_ENABLED = True

# Database
DB_FILE = 'bot.db'
BACKUP_ENABLED = True
BACKUP_INTERVAL_HOURS = 24

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = 'bot.log'

# Validate critical configuration
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in .env file!")

if not BOT_USERNAME:
    raise ValueError("❌ BOT_USERNAME not found in .env file!")

print("✅ Configuration loaded successfully")
print(f"📱 Bot: @{BOT_USERNAME}")
print(f"👤 Admin ID: {ADMIN_ID}")
