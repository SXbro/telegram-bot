import sqlite3
import logging
from typing import Optional, Tuple

class DatabaseHandler:
    def __init__(self, db_path: str = "anonymous_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create messages table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender_id INTEGER,
                        receiver_id INTEGER,
                        message TEXT NOT NULL,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (sender_id) REFERENCES users (user_id),
                        FOREIGN KEY (receiver_id) REFERENCES users (user_id)
                    )
                ''')
                
                conn.commit()
                logging.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logging.error(f"Database initialization error: {e}")
            raise
    
    def add_user(self, user_id: int, username: str = None, 
                 first_name: str = None, last_name: str = None) -> bool:
        """Add or update user in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name) 
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            logging.error(f"Error adding user {user_id}: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Tuple]:
        """Get user information from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name 
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                
                return cursor.fetchone()
                
        except sqlite3.Error as e:
            logging.error(f"Error getting user {user_id}: {e}")
            return None
    
    def save_message(self, sender_id: int, receiver_id: int, message: str) -> bool:
        """Save message to database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO messages (sender_id, receiver_id, message) 
                    VALUES (?, ?, ?)
                ''', (sender_id, receiver_id, message))
                
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            logging.error(f"Error saving message: {e}")
            return False
    
    def get_user_messages(self, user_id: int, limit: int = 50) -> list:
        """Get recent messages received by user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT m.message, m.sent_at 
                    FROM messages m
                    WHERE m.receiver_id = ?
                    ORDER BY m.sent_at DESC
                    LIMIT ?
                ''', (user_id, limit))
                
                return cursor.fetchall()
                
        except sqlite3.Error as e:
            logging.error(f"Error getting messages for user {user_id}: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Get basic statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT COUNT(*) FROM users')
                user_count = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM messages')
                message_count = cursor.fetchone()[0]
                
                return {
                    'total_users': user_count,
                    'total_messages': message_count
                }
                
        except sqlite3.Error as e:
            logging.error(f"Error getting stats: {e}")
            return {'total_users': 0, 'total_messages': 0}
    def get_all_user_ids(self) -> list:
        """Return list of all known user IDs for broadcasting"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users')
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"Error retrieving user list for broadcast: {e}")
            return []
