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
import base64
from cryptography.fernet import Fernet

CONFIG_DB = "/var/hifiberry/config.sqlite"
KEY_FILE = "/etc/configdb.key"

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

    def _get_encryption_key(self):
        """
        Retrieve the encryption key from the key file. If the file does not exist, create it.
        """
        if not os.path.exists(KEY_FILE):
            key = Fernet.generate_key()
            with open(KEY_FILE, "wb") as key_file:
                key_file.write(key)
            os.chmod(KEY_FILE, 0o600)  # Ensure only root can read/write
        else:
            with open(KEY_FILE, "rb") as key_file:
                key = key_file.read()
        return key

    def encrypt_value(self, value):
        """
        Encrypt a value using the encryption key.

        Args:
            value: The value to encrypt (string).

        Returns:
            The encrypted value (string).
        """
        key = self._get_encryption_key()
        fernet = Fernet(key)
        encrypted_value = fernet.encrypt(value.encode())
        return encrypted_value.decode()

    def decrypt_value(self, encrypted_value):
        """
        Decrypt an encrypted value using the encryption key.

        Args:
            encrypted_value: The encrypted value to decrypt (string).

        Returns:
            The decrypted value (string).
        """
        key = self._get_encryption_key()
        fernet = Fernet(key)
        decrypted_value = fernet.decrypt(encrypted_value.encode())
        return decrypted_value.decode()

    def get(self, key, default=None, secure=False):
        """
        Get a value from the database, optionally decrypting it if secure is True.

        Args:
            key: The key to retrieve
            default: Value to return if key doesn't exist
            secure: Whether to decrypt the value

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
                value = result[0]
                if secure:
                    value = self.decrypt_value(value)
                return value
            return default
        except Exception as e:
            logging.error(f"Error getting key {key}: {str(e)}")
            return default

    def set(self, key, value, secure=False):
        """
        Store a key/value pair in the database, optionally encrypting it if secure is True.

        Args:
            key: The key to store
            value: The value to store
            secure: Whether to encrypt the value

        Returns:
            True if successful, False otherwise
        """
        try:
            if secure:
                value = self.encrypt_value(value)

            # First check if the current value matches the new value
            current_value = self.get(key, secure=secure)
            if current_value == value:
                logging.debug(f"Value for {key} is already '{value}', skipping update")
                return True

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO config (key, value, modified_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()
            conn.close()

            if current_value is not None:
                logging.debug(f"Updated key {key} from '{current_value}' to '{value}'")
            else:
                logging.debug(f"Created new key {key} with value '{value}'")

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
    
    # Create arguments for the different commands
    parser.add_argument('--get', metavar='KEY', help='Get a value from the configuration')
    parser.add_argument('--set', nargs=2, metavar=('KEY', 'VALUE'), help='Set a key/value pair')
    parser.add_argument('--delete', metavar='KEY', help='Delete a key')
    parser.add_argument('--list', action='store_true', help='List all keys')
    parser.add_argument('--dump', action='store_true', help='Dump all key/value pairs')
    parser.add_argument('--prefix', help='Filter keys by prefix (for use with --list or --dump)')
    parser.add_argument('--default', help='Default value if key does not exist (for use with --get)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    # Handle positional command syntax as well (for backwards compatibility)
    parser.add_argument('command', nargs='?', help='Legacy command (get, set, delete, list, dump)')
    parser.add_argument('args', nargs='*', help='Legacy command arguments')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize database
    db = ConfigDB()
    
    # Handle commands with preference for new-style (--option) commands
    
    # --get command
    if args.get:
        value = db.get(args.get, args.default)
        if value is not None:
            print(value)
            return 0
        else:
            return 1
            
    # --set command
    elif args.set:
        key, value = args.set
        success = db.set(key, value)
        if not success:
            logging.error(f"Failed to set {key}")
            return 1
        return 0
            
    # --delete command
    elif args.delete:
        success = db.delete(args.delete)
        if not success:
            logging.error(f"Failed to delete {args.delete}")
            return 1
        return 0
            
    # --list command
    elif args.list:
        keys = db.list_keys(args.prefix)
        for key in keys:
            print(key)
        return 0
            
    # --dump command
    elif args.dump:
        entries = db.get_all(args.prefix)
        for key, value in entries.items():
            print(f"{key}={value}")
        return 0
    
    # Handle legacy (positional) syntax if no new-style commands were given
    elif args.command:
        if args.command == 'get' and args.args:
            key = args.args[0]
            default = args.args[1] if len(args.args) > 1 else None
            value = db.get(key, default)
            if value is not None:
                print(value)
                return 0
            else:
                return 1
                
        elif args.command == 'set' and len(args.args) >= 2:
            key = args.args[0]
            value = args.args[1]
            success = db.set(key, value)
            if not success:
                logging.error(f"Failed to set {key}")
                return 1
            return 0
                
        elif args.command == 'delete' and args.args:
            key = args.args[0]
            success = db.delete(key)
            if not success:
                logging.error(f"Failed to delete {key}")
                return 1
            return 0
                
        elif args.command == 'list':
            prefix = args.args[0] if args.args else None
            keys = db.list_keys(prefix)
            for key in keys:
                print(key)
            return 0
                
        elif args.command == 'dump':
            prefix = args.args[0] if args.args else None
            entries = db.get_all(prefix)
            for key, value in entries.items():
                print(f"{key}={value}")
            return 0
    
    # If no action specified, show help
    parser.print_help()
    return 1

if __name__ == "__main__":
    sys.exit(main())