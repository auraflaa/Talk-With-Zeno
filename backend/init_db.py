"""
Initialize SQLite database for Talk With Zeno
Run this script to set up the database with initial schema
"""

import os
import sys

# Add parent directory to path to import database service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.database import Database


def main():
    """Initialize the database"""
    # Get database path from environment or use default
    db_path = os.getenv('DATABASE_PATH', 'data/zeno.db')
    
    print(f"Initializing database at: {db_path}")
    
    # Initialize database (creates tables if they don't exist)
    db = Database(db_path)
    
    print("Database initialized successfully!")
    print(f"Database file: {os.path.abspath(db_path)}")
    
    # Optionally create a default user for testing
    default_user = db.get_user('user_main')
    if not default_user:
        print("\nCreating default user (user_main)...")
        db.create_user(
            user_id='user_main',
            name='Main User',
            email='user@zeno.app',
            avatar_color='bg-primary',
            preferences={
                'tonePreference': 'supportive',
                'depthTolerance': 'moderate',
                'interactionMode': 'text'
            }
        )
        print("Default user created!")
    else:
        print("\nDefault user already exists.")


if __name__ == '__main__':
    main()

