import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import json

DB_FILE = 'bot.db'

def get_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn

def init_db():
    """Initialize database tables with enhanced schema"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create users table with enhanced fields
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            is_bot INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_messages_sent INTEGER DEFAULT 0,
            total_messages_received INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            block_reason TEXT
        )
    ''')
    
    # Create messages table with enhanced tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            content TEXT,
            message_type TEXT DEFAULT 'text',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            read_at TIMESTAMP,
            is_reported INTEGER DEFAULT 0,
            rating INTEGER,
            FOREIGN KEY (from_user_id) REFERENCES users (user_id),
            FOREIGN KEY (to_user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Create user_analytics table for tracking engagement
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date DATE DEFAULT CURRENT_DATE,
            messages_sent INTEGER DEFAULT 0,
            messages_received INTEGER DEFAULT 0,
            active_time_seconds INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            UNIQUE(user_id, date)
        )
    ''')
    
    # Create blocked_users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker_user_id INTEGER,
            blocked_user_id INTEGER,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            FOREIGN KEY (blocker_user_id) REFERENCES users (user_id),
            FOREIGN KEY (blocked_user_id) REFERENCES users (user_id),
            UNIQUE(blocker_user_id, blocked_user_id)
        )
    ''')
    
    # Create reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_user_id INTEGER,
            message_id INTEGER,
            reported_user_id INTEGER,
            reason TEXT,
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (reporter_user_id) REFERENCES users (user_id),
            FOREIGN KEY (message_id) REFERENCES messages (id),
            FOREIGN KEY (reported_user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Create user_settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            notifications_enabled INTEGER DEFAULT 1,
            allow_media INTEGER DEFAULT 1,
            show_read_receipts INTEGER DEFAULT 0,
            language TEXT DEFAULT 'en',
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_to_user ON messages(to_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_from_user ON messages(from_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_user_date ON user_analytics(user_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blocked_users ON blocked_users(blocker_user_id, blocked_user_id)')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with enhanced schema")

def migrate_existing_data():
    """Migrate existing data to new schema (add missing columns)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check and add missing columns to users table
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'last_name' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN last_name TEXT')
        if 'language_code' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN language_code TEXT')
        if 'is_bot' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_bot INTEGER DEFAULT 0')
        if 'is_premium' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0')
        if 'last_active' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        if 'total_messages_sent' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN total_messages_sent INTEGER DEFAULT 0')
        if 'total_messages_received' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN total_messages_received INTEGER DEFAULT 0')
        if 'is_blocked' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0')
        if 'block_reason' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN block_reason TEXT')
        
        # Check and add missing columns to messages table
        cursor.execute("PRAGMA table_info(messages)")
        msg_columns = [col[1] for col in cursor.fetchall()]
        
        if 'message_type' not in msg_columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT "text"')
        if 'is_read' not in msg_columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0')
        if 'read_at' not in msg_columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN read_at TIMESTAMP')
        if 'is_reported' not in msg_columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN is_reported INTEGER DEFAULT 0')
        if 'rating' not in msg_columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN rating INTEGER')
        
        conn.commit()
        print("✅ Database migration completed successfully")
        
    except Exception as e:
        print(f"⚠️ Migration warning: {e}")
        conn.rollback()
    finally:
        conn.close()

def add_user(user_id: int, username: Optional[str], first_name: Optional[str], 
             last_name: Optional[str] = None, language_code: Optional[str] = None,
             is_bot: bool = False, is_premium: bool = False):
    """Add or update user in database with enhanced fields"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, language_code, is_bot, is_premium, join_date, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT join_date FROM users WHERE user_id = ?), CURRENT_TIMESTAMP),
                    CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                language_code = excluded.language_code,
                is_premium = excluded.is_premium,
                last_active = CURRENT_TIMESTAMP
        ''', (user_id, username, first_name, last_name, language_code, 
              1 if is_bot else 0, 1 if is_premium else 0, user_id))
        
        # Create default settings for new users
        cursor.execute('''
            INSERT OR IGNORE INTO user_settings (user_id)
            VALUES (?)
        ''', (user_id,))
        
        conn.commit()
        print(f"✅ User {user_id} ({first_name}) added/updated in database")
        
    except Exception as e:
        print(f"❌ Error adding user {user_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

def update_user_activity(user_id: int):
    """Update user's last active timestamp"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users SET last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
    except Exception as e:
        print(f"❌ Error updating activity for {user_id}: {e}")
    finally:
        conn.close()

def user_exists(user_id: int) -> bool:
    """Check if user exists in database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        print(f"❌ Error checking if user {user_id} exists: {e}")
        return False
    finally:
        conn.close()

def is_user_blocked_by_admin(user_id: int) -> bool:
    """Check if user is blocked by admin"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except Exception as e:
        print(f"❌ Error checking block status: {e}")
        return False
    finally:
        conn.close()

def block_user_by_admin(user_id: int, reason: str = None):
    """Block a user (admin action)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users SET is_blocked = 1, block_reason = ?
            WHERE user_id = ?
        ''', (reason, user_id))
        conn.commit()
        print(f"✅ User {user_id} blocked by admin")
    except Exception as e:
        print(f"❌ Error blocking user: {e}")
    finally:
        conn.close()

def unblock_user_by_admin(user_id: int):
    """Unblock a user (admin action)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users SET is_blocked = 0, block_reason = NULL
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        print(f"✅ User {user_id} unblocked by admin")
    except Exception as e:
        print(f"❌ Error unblocking user: {e}")
    finally:
        conn.close()

def block_user(blocker_id: int, blocked_id: int, reason: str = None):
    """Block a user from sending messages"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO blocked_users (blocker_user_id, blocked_user_id, reason)
            VALUES (?, ?, ?)
        ''', (blocker_id, blocked_id, reason))
        conn.commit()
        print(f"✅ User {blocker_id} blocked {blocked_id}")
    except Exception as e:
        print(f"❌ Error blocking user: {e}")
    finally:
        conn.close()

def unblock_user(blocker_id: int, blocked_id: int):
    """Unblock a user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            DELETE FROM blocked_users 
            WHERE blocker_user_id = ? AND blocked_user_id = ?
        ''', (blocker_id, blocked_id))
        conn.commit()
        print(f"✅ User {blocker_id} unblocked {blocked_id}")
    except Exception as e:
        print(f"❌ Error unblocking user: {e}")
    finally:
        conn.close()

def is_blocked(blocker_id: int, blocked_id: int) -> bool:
    """Check if a user is blocked"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 1 FROM blocked_users 
            WHERE blocker_user_id = ? AND blocked_user_id = ?
        ''', (blocker_id, blocked_id))
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"❌ Error checking block status: {e}")
        return False
    finally:
        conn.close()

def add_message(from_user_id: int, to_user_id: int, content: str, message_type: str = 'text'):
    """Add message to database with enhanced tracking"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO messages (from_user_id, to_user_id, content, message_type)
            VALUES (?, ?, ?, ?)
        ''', (from_user_id, to_user_id, content, message_type))
        
        # Update user message counts
        cursor.execute('''
            UPDATE users SET total_messages_sent = total_messages_sent + 1
            WHERE user_id = ?
        ''', (from_user_id,))
        
        cursor.execute('''
            UPDATE users SET total_messages_received = total_messages_received + 1
            WHERE user_id = ?
        ''', (to_user_id,))
        
        # Update analytics
        cursor.execute('''
            INSERT INTO user_analytics (user_id, date, messages_sent)
            VALUES (?, DATE('now'), 1)
            ON CONFLICT(user_id, date) DO UPDATE SET
                messages_sent = messages_sent + 1
        ''', (from_user_id,))
        
        cursor.execute('''
            INSERT INTO user_analytics (user_id, date, messages_received)
            VALUES (?, DATE('now'), 1)
            ON CONFLICT(user_id, date) DO UPDATE SET
                messages_received = messages_received + 1
        ''', (to_user_id,))
        
        conn.commit()
        print(f"✅ Message saved: {from_user_id} -> {to_user_id} ({message_type})")
        
    except Exception as e:
        print(f"❌ Error saving message: {e}")
        conn.rollback()
    finally:
        conn.close()

def mark_message_read(message_id: int):
    """Mark a message as read"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE messages SET is_read = 1, read_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (message_id,))
        conn.commit()
    except Exception as e:
        print(f"❌ Error marking message read: {e}")
    finally:
        conn.close()

def report_message(reporter_id: int, message_id: int, reported_user_id: int, reason: str):
    """Report a message"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO reports (reporter_user_id, message_id, reported_user_id, reason)
            VALUES (?, ?, ?, ?)
        ''', (reporter_id, message_id, reported_user_id, reason))
        
        cursor.execute('''
            UPDATE messages SET is_reported = 1 WHERE id = ?
        ''', (message_id,))
        
        conn.commit()
        print(f"✅ Message {message_id} reported by {reporter_id}")
    except Exception as e:
        print(f"❌ Error reporting message: {e}")
    finally:
        conn.close()

def get_user_stats() -> Tuple[int, int]:
    """Get user and message statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM messages')
        message_count = cursor.fetchone()[0]
        
        return user_count, message_count
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return 0, 0
    finally:
        conn.close()

def get_user_profile(user_id: int) -> Optional[Dict]:
    """Get user profile with statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT user_id, username, first_name, join_date, last_active,
                   total_messages_sent, total_messages_received, is_premium
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'join_date': row[3],
                'last_active': row[4],
                'messages_sent': row[5],
                'messages_received': row[6],
                'is_premium': row[7]
            }
        return None
    except Exception as e:
        print(f"❌ Error getting user profile: {e}")
        return None
    finally:
        conn.close()

def get_message_history(user_id: int, limit: int = 10) -> List[Dict]:
    """Get recent message history for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id, from_user_id, to_user_id, content, message_type, timestamp, is_read
            FROM messages
            WHERE from_user_id = ? OR to_user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, user_id, limit))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row[0],
                'from_user_id': row[1],
                'to_user_id': row[2],
                'content': row[3],
                'message_type': row[4],
                'timestamp': row[5],
                'is_read': row[6],
                'direction': 'sent' if row[1] == user_id else 'received'
            })
        
        return messages
    except Exception as e:
        print(f"❌ Error getting message history: {e}")
        return []
    finally:
        conn.close()

def get_all_users() -> List[Tuple[int, str, str]]:
    """Get all users for broadcasting"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT user_id, username, first_name 
            FROM users 
            WHERE is_blocked = 0
            ORDER BY join_date DESC
        ''')
        users = cursor.fetchall()
        
        valid_users = []
        for user in users:
            user_id, username, first_name = user
            if user_id and isinstance(user_id, int):
                valid_users.append((user_id, username or '', first_name or ''))
        
        print(f"📊 Retrieved {len(valid_users)} valid users from database")
        return valid_users
    except Exception as e:
        print(f"❌ Error getting users: {e}")
        return []
    finally:
        conn.close()

def get_admin_analytics() -> Dict:
    """Get comprehensive analytics for admin dashboard"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Total stats
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM messages')
        total_messages = cursor.fetchone()[0]
        
        # Active users (last 7 days)
        cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE last_active >= datetime('now', '-7 days')
        ''')
        active_users_7d = cursor.fetchone()[0]
        
        # New users (last 24 hours)
        cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE join_date >= datetime('now', '-1 day')
        ''')
        new_users_24h = cursor.fetchone()[0]
        
        # Messages today
        cursor.execute('''
            SELECT COUNT(*) FROM messages 
            WHERE DATE(timestamp) = DATE('now')
        ''')
        messages_today = cursor.fetchone()[0]
        
        # Pending reports
        cursor.execute('''
            SELECT COUNT(*) FROM reports WHERE status = 'pending'
        ''')
        pending_reports = cursor.fetchone()[0]
        
        # Blocked users count
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
        blocked_users = cursor.fetchone()[0]
        
        return {
            'total_users': total_users,
            'total_messages': total_messages,
            'active_users_7d': active_users_7d,
            'new_users_24h': new_users_24h,
            'messages_today': messages_today,
            'pending_reports': pending_reports,
            'blocked_users': blocked_users
        }
    except Exception as e:
        print(f"❌ Error getting analytics: {e}")
        return {}
    finally:
        conn.close()

def get_user_settings(user_id: int) -> Dict:
    """Get user settings"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT notifications_enabled, allow_media, show_read_receipts, language
            FROM user_settings WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'notifications_enabled': bool(row[0]),
                'allow_media': bool(row[1]),
                'show_read_receipts': bool(row[2]),
                'language': row[3]
            }
        return {
            'notifications_enabled': True,
            'allow_media': True,
            'show_read_receipts': False,
            'language': 'en'
        }
    except Exception as e:
        print(f"❌ Error getting settings: {e}")
        return {}
    finally:
        conn.close()

def update_user_settings(user_id: int, **settings):
    """Update user settings"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Build dynamic update query
        fields = []
        values = []
        for key, value in settings.items():
            if key in ['notifications_enabled', 'allow_media', 'show_read_receipts', 'language']:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if fields:
            values.append(user_id)
            query = f"UPDATE user_settings SET {', '.join(fields)} WHERE user_id = ?"
            cursor.execute(query, values)
            conn.commit()
            print(f"✅ Settings updated for user {user_id}")
    except Exception as e:
        print(f"❌ Error updating settings: {e}")
    finally:
        conn.close()

def get_rate_limit_count(user_id: int, hours: int = 1) -> int:
    """Get message count for rate limiting"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*) FROM messages
            WHERE from_user_id = ? AND timestamp >= datetime('now', ? || ' hours')
        ''', (user_id, f'-{hours}'))
        
        return cursor.fetchone()[0]
    except Exception as e:
        print(f"❌ Error getting rate limit count: {e}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔧 Initializing database...")
    init_db()
    migrate_existing_data()
    print("✅ Database setup complete!")
