import sqlite3
import logging
from typing import List, Tuple, Optional
from contextlib import contextmanager

DB_FILE = 'bot.db'

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER,
                    to_user_id INTEGER,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                    FOREIGN KEY (to_user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
            logger.info("✅ Database initialized successfully")
            
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}", exc_info=True)
        raise


def add_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    """Add or update user in database"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, join_date)
                VALUES (?, ?, ?, COALESCE(
                    (SELECT join_date FROM users WHERE user_id = ?), 
                    CURRENT_TIMESTAMP
                ))
            ''', (user_id, username, first_name, user_id))
            
            conn.commit()
            logger.debug(f"User {user_id} ({first_name}) added/updated")
            
    except Exception as e:
        logger.error(f"Error adding user {user_id}: {e}", exc_info=True)


def user_exists(user_id: int) -> bool:
    """Check if user exists in database"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            exists = result is not None
            logger.debug(f"User {user_id} exists: {exists}")
            return exists
            
    except Exception as e:
        logger.error(f"Error checking user {user_id}: {e}", exc_info=True)
        return False


def add_message(from_user_id: int, to_user_id: int, content: str):
    """Add message to database"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO messages (from_user_id, to_user_id, content)
                VALUES (?, ?, ?)
            ''', (from_user_id, to_user_id, content))
            
            conn.commit()
            logger.debug(f"Message saved: {from_user_id} -> {to_user_id}")
            
    except Exception as e:
        logger.error(f"Error saving message: {e}", exc_info=True)


def get_user_stats() -> Tuple[int, int]:
    """Get user and message statistics"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Get user count
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]
            
            # Get message count
            cursor.execute('SELECT COUNT(*) FROM messages')
            message_count = cursor.fetchone()[0]
            
            return user_count, message_count
            
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        return 0, 0


def get_all_users() -> List[Tuple[int, str, str]]:
    """Get all users for broadcasting"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, username, first_name 
                FROM users 
                ORDER BY join_date DESC
            ''')
            users = cursor.fetchall()
            
            # Filter valid users
            valid_users = []
            for user in users:
                user_id, username, first_name = user
                if user_id and isinstance(user_id, int):
                    valid_users.append((
                        user_id, 
                        username or '', 
                        first_name or 'Unknown'
                    ))
            
            logger.debug(f"Retrieved {len(valid_users)} users from database")
            return valid_users
            
    except Exception as e:
        logger.error(f"Error getting users: {e}", exc_info=True)
        return []


def get_user_info(user_id: int) -> Optional[Tuple[str, str]]:
    """Get user info by ID"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT username, first_name 
                FROM users 
                WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            return result if result else None
            
    except Exception as e:
        logger.error(f"Error getting user info for {user_id}: {e}", exc_info=True)
        return None
