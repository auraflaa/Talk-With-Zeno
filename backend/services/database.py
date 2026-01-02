"""
SQLite Database Service for Talk With Zeno
Handles user identity and account storage
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any


class Database:
    """SQLite database service for user management"""
    
    def __init__(self, db_path: str = 'data/zeno.db'):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
        
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper settings"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        # Enable foreign keys and optimize for concurrent access
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')  # Write-Ahead Logging for better concurrency
        return conn
    
    def init_db(self):
        """Initialize database and create tables if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create users table with improved schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                avatar_color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                preferences TEXT
            )
        ''')
        
        # Add updated_at column if it doesn't exist (migration)
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)')
        
        conn.commit()
        conn.close()
        print(f"Database initialized at {self.db_path}")
    
    def create_user(self, user_id: str, name: str, email: str, avatar_color: str = "bg-primary", preferences: Optional[Dict[str, Any]] = None) -> bool:
        """
        Create a new user
        
        Args:
            user_id: Unique user identifier
            name: User's display name
            email: User's email address
            avatar_color: Avatar color class
            preferences: Optional preferences dictionary
            
        Returns:
            True if user created successfully, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            preferences_json = json.dumps(preferences) if preferences else None
            
            cursor.execute('''
                INSERT INTO users (id, name, email, avatar_color, preferences)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, name, email, avatar_color, preferences_json))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError as e:
            print(f"Error creating user: {e}")
            return False
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID
        
        Args:
            user_id: User identifier
            
        Returns:
            User dictionary or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            user = dict(row)
            # Parse preferences JSON if present
            if user.get('preferences'):
                try:
                    user['preferences'] = json.loads(user['preferences'])
                except json.JSONDecodeError:
                    user['preferences'] = {}
            return user
        return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email
        
        Args:
            email: User's email address
            
        Returns:
            User dictionary or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            user = dict(row)
            # Parse preferences JSON if present
            if user.get('preferences'):
                try:
                    user['preferences'] = json.loads(user['preferences'])
                except json.JSONDecodeError:
                    user['preferences'] = {}
            return user
        return None
    
    def update_user(self, user_id: str, name: Optional[str] = None, email: Optional[str] = None, 
                   avatar_color: Optional[str] = None, preferences: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update user information
        
        Args:
            user_id: User identifier
            name: Updated name (optional)
            email: Updated email (optional)
            avatar_color: Updated avatar color (optional)
            preferences: Updated preferences (optional)
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            updates = []
            values = []
            
            if name is not None:
                updates.append('name = ?')
                values.append(name)
            if email is not None:
                updates.append('email = ?')
                values.append(email)
            if avatar_color is not None:
                updates.append('avatar_color = ?')
                values.append(avatar_color)
            if preferences is not None:
                updates.append('preferences = ?')
                values.append(json.dumps(preferences))
            
            if not updates:
                conn.close()
                return False
            
            # Always update updated_at timestamp
            updates.append('updated_at = CURRENT_TIMESTAMP')
            values.append(user_id)
            query = f'UPDATE users SET {", ".join(updates)} WHERE id = ?'
            
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating user: {e}")
            return False
    
    def delete_user(self, user_id: str) -> bool:
        """
        Delete user by ID
        
        Args:
            user_id: User identifier
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()
            return deleted
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False
    
    def list_users(self) -> list[Dict[str, Any]]:
        """
        List all users
        
        Returns:
            List of user dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            user = dict(row)
            # Parse preferences JSON if present
            if user.get('preferences'):
                try:
                    user['preferences'] = json.loads(user['preferences'])
                except json.JSONDecodeError:
                    user['preferences'] = {}
            users.append(user)
        
        return users


# Singleton instance
_db_instance: Optional[Database] = None


def get_database(db_path: Optional[str] = None) -> Database:
    """
    Get database instance (singleton pattern)
    
    Args:
        db_path: Optional database path (uses default if not provided)
        
    Returns:
        Database instance
    """
    global _db_instance
    
    if _db_instance is None:
        if db_path:
            _db_instance = Database(db_path)
        else:
            # Try to get from environment variable
            import os
            db_path = os.getenv('DATABASE_PATH', 'data/zeno.db')
            _db_instance = Database(db_path)
    
    return _db_instance

