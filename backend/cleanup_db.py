"""
Database cleanup and maintenance script
Analyzes and cleans up the database, removes orphaned data
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.database import Database
from backend.services.storage_service import StorageService


def analyze_database(db: Database):
    """Analyze database structure and content"""
    print("\n" + "="*60)
    print("DATABASE ANALYSIS")
    print("="*60)
    
    users = db.list_users()
    print(f"\nTotal users: {len(users)}")
    
    if users:
        print("\nUsers:")
        for user in users:
            print(f"  - {user['id']}: {user['name']} ({user['email']})")
            print(f"    Created: {user.get('created_at', 'N/A')}")
            if user.get('preferences'):
                print(f"    Preferences: {len(user['preferences'])} keys")
    
    # Check for orphaned data
    print("\n" + "-"*60)
    print("Checking for issues...")
    
    # Check for duplicate emails
    emails = {}
    for user in users:
        email = user['email']
        if email in emails:
            print(f"  [WARNING] Duplicate email found: {email}")
        emails[email] = user['id']
    
    # Check for missing required fields
    for user in users:
        if not user.get('name'):
            print(f"  [WARNING] User {user['id']} missing name")
        if not user.get('email'):
            print(f"  [WARNING] User {user['id']} missing email")
    
    print("\nDatabase analysis complete!")


def cleanup_orphaned_files(storage: StorageService):
    """Remove orphaned conversation files (no matching user)"""
    print("\n" + "="*60)
    print("STORAGE CLEANUP")
    print("="*60)
    
    chats_path = storage.chats_path
    if not chats_path.exists():
        print("No chats directory found.")
        return
    
    # Get all user IDs from database
    db = Database()
    users = db.list_users()
    valid_user_ids = {user['id'] for user in users}
    
    # Scan chat directories
    orphaned_dirs = []
    orphaned_files = []
    total_files = 0
    total_size = 0
    
    for user_dir in chats_path.iterdir():
        if not user_dir.is_dir():
            continue
        
        user_id = user_dir.name
        total_files += len(list(user_dir.glob("*.json")))
        
        # Check if user exists
        if user_id not in valid_user_ids:
            orphaned_dirs.append(user_dir)
            orphaned_files.extend(user_dir.glob("*.json"))
            for f in user_dir.glob("*.json"):
                total_size += f.stat().st_size
        else:
            # Check file sizes and dates
            for conv_file in user_dir.glob("*.json"):
                file_size = conv_file.stat().st_size
                total_size += file_size
                
                # Check for very old files (optional: can be configured)
                file_time = datetime.fromtimestamp(conv_file.stat().st_mtime)
                age_days = (datetime.now() - file_time).days
                
                if age_days > 365:  # Files older than 1 year
                    print(f"  [INFO] Old conversation file: {conv_file.name} ({age_days} days old)")
    
    print(f"\nTotal conversation files: {total_files}")
    print(f"Total storage size: {total_size / 1024 / 1024:.2f} MB")
    
    if orphaned_dirs:
        print(f"\n[WARNING] Found {len(orphaned_dirs)} orphaned user directories:")
        for dir_path in orphaned_dirs:
            file_count = len(list(dir_path.glob("*.json")))
            print(f"  - {dir_path.name}: {file_count} files")
        
        response = input("\nDelete orphaned directories? (y/N): ").strip().lower()
        if response == 'y':
            for dir_path in orphaned_dirs:
                import shutil
                shutil.rmtree(dir_path)
                print(f"  [DELETED] {dir_path}")
            print("\nCleanup complete!")
        else:
            print("\nCleanup skipped.")
    else:
        print("\n[OK] No orphaned files found!")


def optimize_database(db: Database):
    """Optimize database with indexes and cleanup"""
    print("\n" + "="*60)
    print("DATABASE OPTIMIZATION")
    print("="*60)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Check existing indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    existing_indexes = [row[0] for row in cursor.fetchall()]
    print(f"\nExisting indexes: {existing_indexes}")
    
    # Create indexes if they don't exist
    indexes_to_create = [
        ("idx_users_email", "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"),
        ("idx_users_created_at", "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)"),
    ]
    
    for index_name, index_sql in indexes_to_create:
        if index_name not in existing_indexes:
            cursor.execute(index_sql)
            print(f"  [CREATED] Index: {index_name}")
        else:
            print(f"  [EXISTS] Index: {index_name}")
    
    # Vacuum database (reclaim space)
    print("\nRunning VACUUM to optimize database...")
    cursor.execute("VACUUM")
    
    conn.commit()
    conn.close()
    
    print("[OK] Database optimized!")


def main():
    """Main cleanup function"""
    print("="*60)
    print("Talk With Zeno - Database Cleanup & Analysis")
    print("="*60)
    
    # Initialize services
    db_path = os.getenv('DATABASE_PATH', 'data/zeno.db')
    db = Database(db_path)
    storage = StorageService()
    
    # Run analysis
    analyze_database(db)
    
    # Optimize database
    optimize_database(db)
    
    # Cleanup orphaned files
    cleanup_orphaned_files(storage)
    
    print("\n" + "="*60)
    print("CLEANUP COMPLETE!")
    print("="*60)


if __name__ == '__main__':
    main()

