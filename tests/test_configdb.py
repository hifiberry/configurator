#!/usr/bin/env python3
"""
Regression tests for ConfigDB module

Tests cover:
- Basic key/value operations (get, set, delete)
- Encrypted (secure) value handling
- Database initialization and persistence
- Prefix filtering
- Error handling and edge cases
- Flask handler integration (if available)
"""

import unittest
import tempfile
import os
import sys
import shutil
from unittest.mock import patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from configdb import ConfigDB
from cryptography.fernet import InvalidToken


class TestConfigDBInitialization(unittest.TestCase):
    """Test database initialization and setup"""

    def setUp(self):
        """Create a temporary database for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_db_initialization_creates_file(self):
        """Test that initializing ConfigDB creates the database file"""
        ConfigDB(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))

    def test_db_initialization_creates_directory(self):
        """Test that initializing ConfigDB creates missing parent directories"""
        nested_path = os.path.join(self.temp_dir, 'nested', 'deep', 'test.db')
        ConfigDB(nested_path)
        self.assertTrue(os.path.exists(nested_path))

    def test_db_creates_table_structure(self):
        """Test that the config table is created with correct schema"""
        ConfigDB(self.db_path)
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
        result = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(result)


class TestBasicKeyValueOperations(unittest.TestCase):
    """Test basic get, set, delete operations"""

    def setUp(self):
        """Create a temporary database for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.db = ConfigDB(self.db_path)

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_set_and_get_string_value(self):
        """Test setting and retrieving a simple string value"""
        self.assertTrue(self.db.set('key1', 'value1'))
        self.assertEqual(self.db.get('key1'), 'value1')

    def test_set_and_get_multiple_values(self):
        """Test setting and retrieving multiple values"""
        self.db.set('key1', 'value1')
        self.db.set('key2', 'value2')
        self.db.set('key3', 'value3')
        
        self.assertEqual(self.db.get('key1'), 'value1')
        self.assertEqual(self.db.get('key2'), 'value2')
        self.assertEqual(self.db.get('key3'), 'value3')

    def test_get_nonexistent_key_returns_none(self):
        """Test that getting a non-existent key returns None"""
        result = self.db.get('nonexistent')
        self.assertIsNone(result)

    def test_get_nonexistent_key_returns_default(self):
        """Test that getting a non-existent key returns the provided default"""
        result = self.db.get('nonexistent', default='default_value')
        self.assertEqual(result, 'default_value')

    def test_overwrite_existing_value(self):
        """Test overwriting an existing value"""
        self.db.set('key1', 'original_value')
        self.db.set('key1', 'new_value')
        self.assertEqual(self.db.get('key1'), 'new_value')

    def test_set_same_value_returns_true(self):
        """Test that setting the same value again returns True without updating"""
        self.assertTrue(self.db.set('key1', 'value1'))
        self.assertTrue(self.db.set('key1', 'value1'))

    def test_delete_existing_key(self):
        """Test deleting an existing key"""
        self.db.set('key1', 'value1')
        self.assertTrue(self.db.delete('key1'))
        self.assertIsNone(self.db.get('key1'))

    def test_delete_nonexistent_key_returns_true(self):
        """Test that deleting a non-existent key returns True (no-op)"""
        result = self.db.delete('nonexistent')
        self.assertTrue(result)

    def test_numeric_values_stored_as_strings(self):
        """Test that numeric values are stored and retrieved correctly"""
        self.db.set('number', '42')
        result = self.db.get('number')
        self.assertEqual(result, '42')

    def test_empty_string_value(self):
        """Test storing and retrieving empty strings"""
        self.db.set('empty', '')
        self.assertEqual(self.db.get('empty'), '')


class TestSecureKeyValueOperations(unittest.TestCase):
    """Test encrypted/secure key/value operations"""

    def setUp(self):
        """Create a temporary database and key file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.key_path = os.path.join(self.temp_dir, 'test.key')
        
        # Patch the KEY_FILE path
        self.key_file_patcher = patch('configdb.KEY_FILE', self.key_path)
        self.key_file_patcher.start()
        
        self.db = ConfigDB(self.db_path)

    def tearDown(self):
        """Clean up temporary database and key file"""
        self.key_file_patcher.stop()
        for path in [self.db_path, self.key_path]:
            if os.path.exists(path):
                os.remove(path)
        shutil.rmtree(self.temp_dir)

    def test_set_and_get_secure_value(self):
        """Test setting and retrieving a secure (encrypted) value"""
        self.assertTrue(self.db.set('secure_key', 'secret_value', secure=True))
        result = self.db.get('secure_key', secure=True)
        self.assertEqual(result, 'secret_value')

    def test_secure_value_stored_encrypted(self):
        """Test that secure values are actually encrypted in storage"""
        self.db.set('secure_key', 'secret_value', secure=True)
        
        # Get the raw encrypted value from database
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", ('secure_key',))
        stored_value = cursor.fetchone()[0]
        conn.close()
        
        # Encrypted value should not match the original
        self.assertNotEqual(stored_value, 'secret_value')

    def test_cannot_decrypt_secure_value_without_secure_flag(self):
        """Test that retrieving a secure value without secure=True returns encrypted data"""
        self.db.set('secure_key', 'secret_value', secure=True)
        encrypted_value = self.db.get('secure_key', secure=False)
        # Should get the encrypted string, not the original value
        self.assertNotEqual(encrypted_value, 'secret_value')

    def test_set_same_secure_value_twice(self):
        """Test that setting the same secure value twice is detected as idempotent"""
        self.db.set('secure_key', 'secret_value', secure=True)
        result = self.db.set('secure_key', 'secret_value', secure=True)
        # Should return True (value already set, no update needed)
        self.assertTrue(result)

    def test_overwrite_secure_value(self):
        """Test overwriting a secure value with a different value"""
        self.db.set('secure_key', 'original_secret', secure=True)
        self.db.set('secure_key', 'new_secret', secure=True)
        result = self.db.get('secure_key', secure=True)
        self.assertEqual(result, 'new_secret')

    def test_secure_key_file_created_with_correct_permissions(self):
        """Test that the encryption key file is created with secure permissions"""
        if os.path.exists(self.key_path):
            os.remove(self.key_path)
        
        self.db.set('key', 'value', secure=True)
        
        # Check that key file exists and has correct permissions
        self.assertTrue(os.path.exists(self.key_path))
        file_mode = os.stat(self.key_path).st_mode & 0o777
        # Should be 0o600 (read/write for owner only)
        self.assertEqual(file_mode, 0o600)


class TestListingAndFiltering(unittest.TestCase):
    """Test key listing and prefix filtering"""

    def setUp(self):
        """Create a temporary database with test data"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.db = ConfigDB(self.db_path)
        
        # Set up test data with various prefixes
        self.db.set('user:name', 'John')
        self.db.set('user:email', 'john@example.com')
        self.db.set('system:version', '1.0')
        self.db.set('system:arch', 'arm64')
        self.db.set('other', 'value')

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_list_all_keys(self):
        """Test listing all keys without filtering"""
        keys = self.db.list_keys()
        expected = {'user:name', 'user:email', 'system:version', 'system:arch', 'other'}
        self.assertEqual(set(keys), expected)

    def test_list_keys_with_prefix(self):
        """Test listing keys filtered by prefix"""
        keys = self.db.list_keys('user:')
        expected = {'user:name', 'user:email'}
        self.assertEqual(set(keys), expected)

    def test_list_keys_with_prefix_no_matches(self):
        """Test listing keys with prefix that matches nothing"""
        keys = self.db.list_keys('nonexistent:')
        self.assertEqual(len(keys), 0)

    def test_get_all_key_value_pairs(self):
        """Test getting all key/value pairs"""
        all_data = self.db.get_all()
        self.assertEqual(len(all_data), 5)
        self.assertEqual(all_data['user:name'], 'John')
        self.assertEqual(all_data['system:version'], '1.0')

    def test_get_all_with_prefix(self):
        """Test getting all key/value pairs filtered by prefix"""
        user_data = self.db.get_all('user:')
        expected = {'user:name': 'John', 'user:email': 'john@example.com'}
        self.assertEqual(user_data, expected)

    def test_empty_list_on_empty_database(self):
        """Test listing keys on an empty database"""
        empty_db_path = os.path.join(self.temp_dir, 'empty.db')
        empty_db = ConfigDB(empty_db_path)
        keys = empty_db.list_keys()
        self.assertEqual(len(keys), 0)


class TestClearAllOperation(unittest.TestCase):
    """Test the clear_all operation"""

    def setUp(self):
        """Create a temporary database with test data"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.db = ConfigDB(self.db_path)

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_clear_all_removes_all_keys(self):
        """Test that clear_all removes all keys from the database"""
        self.db.set('key1', 'value1')
        self.db.set('key2', 'value2')
        self.db.set('key3', 'value3')
        
        self.assertTrue(self.db.clear_all())
        
        # Verify all keys are gone
        keys = self.db.list_keys()
        self.assertEqual(len(keys), 0)

    def test_clear_all_on_empty_database(self):
        """Test clear_all on an already empty database"""
        result = self.db.clear_all()
        self.assertTrue(result)

    def test_clear_all_returns_true(self):
        """Test that clear_all returns True on success"""
        self.db.set('key', 'value')
        result = self.db.clear_all()
        self.assertTrue(result)


class TestEncryptionErrorHandling(unittest.TestCase):
    """Test error handling in encryption/decryption"""

    def setUp(self):
        """Create a temporary database and key file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.key_path = os.path.join(self.temp_dir, 'test.key')
        
        self.key_file_patcher = patch('configdb.KEY_FILE', self.key_path)
        self.key_file_patcher.start()
        
        self.db = ConfigDB(self.db_path)

    def tearDown(self):
        """Clean up temporary database and key file"""
        self.key_file_patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_decrypt_corrupted_value_raises_error(self):
        """Test that decrypting a corrupted value raises InvalidToken"""
        with self.assertRaises(InvalidToken):
            self.db.decrypt_value('not_a_valid_encrypted_value')

    def test_set_with_secure_recovers_from_corrupted_value(self):
        """Test that set() handles corrupted encrypted values gracefully"""
        import sqlite3
        
        # Store a corrupted encrypted value directly
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            ('corrupted_key', 'this_is_not_valid_encryption')
        )
        conn.commit()
        conn.close()
        
        # Try to set the same key with secure=True - should succeed and replace
        result = self.db.set('corrupted_key', 'new_value', secure=True)
        self.assertTrue(result)

    def test_get_secure_with_corrupted_value_returns_encrypted(self):
        """Test that getting a corrupted secure value as non-secure returns the raw value"""
        import sqlite3
        
        # Store a corrupted encrypted value directly
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            ('corrupted_key', 'this_is_not_valid_encryption')
        )
        conn.commit()
        conn.close()
        
        # Get without secure flag
        result = self.db.get('corrupted_key', secure=False)
        self.assertEqual(result, 'this_is_not_valid_encryption')


class TestPersistence(unittest.TestCase):
    """Test that data persists between sessions"""

    def setUp(self):
        """Create a temporary database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_data_persists_across_db_instances(self):
        """Test that data written by one instance is readable by another"""
        # Create first instance and set values
        db1 = ConfigDB(self.db_path)
        db1.set('key1', 'value1')
        db1.set('key2', 'value2')
        
        # Create second instance and verify values
        db2 = ConfigDB(self.db_path)
        self.assertEqual(db2.get('key1'), 'value1')
        self.assertEqual(db2.get('key2'), 'value2')

    def test_encrypted_data_persists(self):
        """Test that encrypted data persists across instances"""
        self.key_path = os.path.join(self.temp_dir, 'test.key')
        
        with patch('configdb.KEY_FILE', self.key_path):
            db1 = ConfigDB(self.db_path)
            db1.set('secure_key', 'secret_value', secure=True)
            
            # Create new instance with same key file
            db2 = ConfigDB(self.db_path)
            result = db2.get('secure_key', secure=True)
            self.assertEqual(result, 'secret_value')


class TestFlaskHandlers(unittest.TestCase):
    """Test Flask HTTP handler methods"""

    def setUp(self):
        """Create a temporary database for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.db = ConfigDB(self.db_path)
        
        # Populate test data
        self.db.set('test_key', 'test_value')

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_flask_handlers_raise_error_when_flask_unavailable(self):
        """Test that Flask handlers raise error when Flask is not available"""
        # Create a ConfigDB instance with Flask imports disabled
        with patch('configdb.request', None):
            with patch('configdb.jsonify', None):
                db = ConfigDB(self.db_path)
                
                with self.assertRaises(RuntimeError) as context:
                    db.handle_get_config_keys()
                
                self.assertIn('Flask', str(context.exception))

    @patch('configdb.jsonify')
    @patch('configdb.request')
    def test_handle_get_config_keys(self, mock_request, mock_jsonify):
        """Test handle_get_config_keys Flask handler"""
        mock_request.args.get.return_value = None
        mock_jsonify.return_value = {'status': 'success'}
        
        result = self.db.handle_get_config_keys()
        
        mock_request.args.get.assert_called_once_with('prefix')
        self.assertIsNotNone(result)

    @patch('configdb.jsonify')
    @patch('configdb.request')
    def test_handle_get_config_value(self, mock_request, mock_jsonify):
        """Test handle_get_config_value Flask handler"""
        mock_request.args.get.side_effect = lambda key, default=None: 'false' if key == 'secure' else None
        mock_jsonify.return_value = {'status': 'success'}
        
        result = self.db.handle_get_config_value('test_key')
        
        self.assertIsNotNone(result)

    @patch('configdb.jsonify')
    @patch('configdb.request')
    def test_handle_set_config_value(self, mock_request, mock_jsonify):
        """Test handle_set_config_value Flask handler"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'value': 'new_value', 'secure': False}
        mock_jsonify.return_value = {'status': 'success'}
        
        result = self.db.handle_set_config_value('new_key')
        
        self.assertIsNotNone(result)

    @patch('configdb.jsonify')
    @patch('configdb.request')
    def test_handle_delete_config_value(self, mock_request, mock_jsonify):
        """Test handle_delete_config_value Flask handler"""
        mock_jsonify.return_value = {'status': 'success'}
        
        result = self.db.handle_delete_config_value('test_key')
        
        self.assertIsNotNone(result)


class TestEdgeCasesAndRobustness(unittest.TestCase):
    """Test edge cases and error scenarios"""

    def setUp(self):
        """Create a temporary database for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.db = ConfigDB(self.db_path)

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_special_characters_in_values(self):
        """Test handling special characters in values"""
        special_value = "!@#$%^&*()_+-=[]{}|;':\",./<>?\\n\\t"
        self.db.set('special', special_value)
        result = self.db.get('special')
        self.assertEqual(result, special_value)

    def test_unicode_characters_in_values(self):
        """Test handling Unicode characters in values"""
        unicode_value = "Hello 世界 🌍 مرحبا мир"
        self.db.set('unicode', unicode_value)
        result = self.db.get('unicode')
        self.assertEqual(result, unicode_value)

    def test_very_long_values(self):
        """Test handling very long string values"""
        long_value = 'x' * 100000  # 100KB string
        self.db.set('long', long_value)
        result = self.db.get('long')
        self.assertEqual(result, long_value)

    def test_very_long_key_names(self):
        """Test handling very long key names"""
        long_key = 'key:' + 'a' * 1000
        self.db.set(long_key, 'value')
        result = self.db.get(long_key)
        self.assertEqual(result, 'value')

    def test_key_with_special_characters(self):
        """Test keys with special characters"""
        special_key = "key:with:colons/slashes:and-dashes"
        self.db.set(special_key, 'value')
        result = self.db.get(special_key)
        self.assertEqual(result, 'value')

    def test_case_sensitive_keys(self):
        """Test that keys are case-sensitive"""
        self.db.set('Key', 'value1')
        self.db.set('key', 'value2')
        self.db.set('KEY', 'value3')
        
        self.assertEqual(self.db.get('Key'), 'value1')
        self.assertEqual(self.db.get('key'), 'value2')
        self.assertEqual(self.db.get('KEY'), 'value3')

    def test_newlines_in_values(self):
        """Test handling newlines in values"""
        multiline_value = "line1\nline2\nline3"
        self.db.set('multiline', multiline_value)
        result = self.db.get('multiline')
        self.assertEqual(result, multiline_value)

    def test_null_like_strings(self):
        """Test handling null-like string values"""
        for null_like in ['null', 'None', 'NULL', '']:
            self.db.set('null_test', null_like)
            result = self.db.get('null_test')
            self.assertEqual(result, null_like)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
