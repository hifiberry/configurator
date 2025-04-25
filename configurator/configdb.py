#!/usr/bin/env python3
"""
HiFiBerry Configuration Database

A simple key/value store for HiFiBerry OS configuration using SQLite
"""

import os
import sys
import sqlite3
import logging
import argparse

CONFIG_DB = "/var/hifiberry/config.sqlite"

class ConfigDB:
    """
    A class to manage key/value pairs in a SQLite database
    """

    def __init__(self, db_path=CONFIG_DB):
        """
        Initialize the database connection
        
        Args:
            db_path: Path to the SQLite database file (default: /var/hifiberry/config.sqlite)
        """
        self.db_path = db_path
        self._ensure_db_exists()
        
    def _ensure_db_exists(self):
        """Create the database and table if they don't exist"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
                logging.error(f"Couldn't create directory {db_dir}: {str(e)}")
                return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Couldn't initialize database: {str(e)}")
            return False

    def get(self, key, default=None):
        """
        Get a value from the database
        
        Args:
            key: The key to retrieve
            default: Value to return if key doesn't exist
            
        Returns:
            The value for the key or default if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            return default
        except Exception as e:
            logging.error(f"Error getting key {key}: {str(e)}")
            return default
    
    def set(self, key, value):
        """
        Store a key/value pair in the database
        
        Args:
            key: The key to store
            value: The value to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO config (key, value, modified_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error setting key {key}: {str(e)}")
            return False
    
    def delete(self, key):
        """
        Delete a key from the database
        
        Args:
            key: The key to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM config WHERE key = ?", (key,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error deleting key {key}: {str(e)}")
            return False
    
    def list_keys(self, prefix=None):
        """
        List all keys in the database, optionally filtered by prefix
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            List of keys
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if prefix:
                cursor.execute("SELECT key FROM config WHERE key LIKE ?", (prefix + "%",))
            else:
                cursor.execute("SELECT key FROM config")
                
            keys = [row[0] for row in cursor.fetchall()]
            conn.close()
            return keys
        except Exception as e:
            logging.error(f"Error listing keys: {str(e)}")
            return []
    
    def get_all(self, prefix=None):
        """
        Get all key/value pairs, optionally filtered by prefix
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            Dictionary of key/value pairs
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if prefix:
                cursor.execute("SELECT key, value FROM config WHERE key LIKE ?", (prefix + "%",))
            else:
                cursor.execute("SELECT key, value FROM config")
                
            result = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return result
        except Exception as e:
            logging.error(f"Error getting all keys: {str(e)}")
            return {}

def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s: %(message)s')

    # Create the parser
    parser = argparse.ArgumentParser(description='Manage HiFiBerry OS configuration database')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Get command
    parser_get = subparsers.add_parser('get', help='Get a value from the configuration')
    parser_get.add_argument('key', help='Key to retrieve')
    parser_get.add_argument('--default', help='Default value if key does not exist')
    
    # Set command
    parser_set = subparsers.add_parser('set', help='Set a key/value pair')
    parser_set.add_argument('key', help='Key to set')
    parser_set.add_argument('value', help='Value to store')
    
    # Delete command
    parser_delete = subparsers.add_parser('delete', help='Delete a key')
    parser_delete.add_argument('key', help='Key to delete')
    
    # List command
    parser_list = subparsers.add_parser('list', help='List all keys')
    parser_list.add_argument('--prefix', help='Filter keys by prefix')
    
    # Dump command
    parser_dump = subparsers.add_parser('dump', help='Dump all key/value pairs')
    parser_dump.add_argument('--prefix', help='Filter keys by prefix')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle no command
    if not args.command:
        parser.print_help()
        return 1
    
    # Initialize database
    db = ConfigDB()
    
    # Execute command
    if args.command == 'get':
        value = db.get(args.key, args.default)
        if value is not None:
            print(value)
        else:
            return 1
            
    elif args.command == 'set':
        success = db.set(args.key, args.value)
        if not success:
            logging.error(f"Failed to set {args.key}")
            return 1
            
    elif args.command == 'delete':
        success = db.delete(args.key)
        if not success:
            logging.error(f"Failed to delete {args.key}")
            return 1
            
    elif args.command == 'list':
        keys = db.list_keys(args.prefix)
        for key in keys:
            print(key)
            
    elif args.command == 'dump':
        entries = db.get_all(args.prefix)
        for key, value in entries.items():
            print(f"{key}={value}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())