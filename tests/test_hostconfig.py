#!/usr/bin/env python3
"""
Regression tests for Host Configuration module

Tests cover:
- Hosts file reading and writing
- Hostname retrieval and setting
- Hostname validation and sanitization
- Command-line interface
- Error handling and edge cases
"""

import unittest
import sys
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

# Add src directory to path for imports
sys.path.insert(0, '/home/ulf/data/configurator')

from src.hostconfig import (
    read_hosts_file, write_hosts_file, update_hosts_file,
    get_current_hostname, set_hostname_with_hosts_update,
    validate_hostname, sanitize_hostname, main
)


class TestValidateHostname(unittest.TestCase):
    """Test hostname validation"""

    def test_valid_single_label_hostname(self):
        """Test valid single-label hostname"""
        self.assertTrue(validate_hostname('localhost'))
        self.assertTrue(validate_hostname('hifiberry'))
        self.assertTrue(validate_hostname('myhost'))

    def test_valid_multi_label_hostname(self):
        """Test valid multi-label hostname"""
        self.assertTrue(validate_hostname('my-host'))
        self.assertTrue(validate_hostname('my-host-name'))
        self.assertTrue(validate_hostname('host1'))
        self.assertTrue(validate_hostname('host123'))

    def test_valid_hostname_with_numbers(self):
        """Test valid hostname with numbers"""
        self.assertTrue(validate_hostname('host1'))
        self.assertTrue(validate_hostname('test2'))
        self.assertTrue(validate_hostname('a1b2c3'))

    def test_invalid_hostname_empty(self):
        """Test empty hostname is invalid"""
        self.assertFalse(validate_hostname(''))

    def test_invalid_hostname_too_long(self):
        """Test hostname longer than 64 chars is invalid"""
        long_hostname = 'a' * 65
        self.assertFalse(validate_hostname(long_hostname))

    def test_invalid_hostname_starts_with_hyphen(self):
        """Test hostname starting with hyphen is invalid"""
        self.assertFalse(validate_hostname('-hostname'))

    def test_invalid_hostname_ends_with_hyphen(self):
        """Test hostname ending with hyphen is invalid"""
        self.assertFalse(validate_hostname('hostname-'))

    def test_invalid_hostname_special_characters(self):
        """Test hostname with special characters is invalid"""
        self.assertFalse(validate_hostname('host@name'))
        self.assertFalse(validate_hostname('host_name'))
        self.assertFalse(validate_hostname('host.name'))
        self.assertFalse(validate_hostname('host name'))

    def test_invalid_hostname_uppercase_letters(self):
        """Test that uppercase letters are allowed"""
        # RFC 1123 allows uppercase, but typically lowercase is used
        self.assertTrue(validate_hostname('HostName'))
        self.assertTrue(validate_hostname('HOSTNAME'))

    def test_valid_label_exactly_63_chars(self):
        """Test that label of exactly 63 chars is valid"""
        label = 'a' * 63
        self.assertTrue(validate_hostname(label))

    def test_invalid_label_more_than_63_chars(self):
        """Test that label longer than 63 chars is invalid"""
        label = 'a' * 64
        self.assertFalse(validate_hostname(label))

    def test_boundary_hostname_63_chars_valid(self):
        """Test hostname of 63 characters is valid"""
        hostname = 'a' * 63
        self.assertTrue(validate_hostname(hostname))


class TestSanitizeHostname(unittest.TestCase):
    """Test hostname sanitization"""

    def test_sanitize_simple_hostname(self):
        """Test sanitizing a simple hostname"""
        result = sanitize_hostname('my-host')
        self.assertEqual(result, 'my-host')

    def test_sanitize_with_spaces(self):
        """Test sanitizing hostname with spaces"""
        result = sanitize_hostname('my host')
        self.assertEqual(result, 'my-host')

    def test_sanitize_uppercase_to_lowercase(self):
        """Test converting uppercase to lowercase"""
        result = sanitize_hostname('MyHost')
        self.assertEqual(result, 'myhost')

    def test_sanitize_with_special_characters(self):
        """Test removing special characters"""
        result = sanitize_hostname('my@host#name!')
        self.assertEqual(result, 'myhostname')

    def test_sanitize_multiple_spaces(self):
        """Test multiple spaces converted to single hyphen"""
        result = sanitize_hostname('my   host')
        # Multiple consecutive hyphens are collapsed to single hyphen
        self.assertIn('my-host', result)

    def test_sanitize_leading_hyphen_removed(self):
        """Test leading hyphen removed"""
        result = sanitize_hostname('-hostname')
        self.assertEqual(result, 'hostname')

    def test_sanitize_trailing_hyphen_removed(self):
        """Test trailing hyphen removed"""
        result = sanitize_hostname('hostname-')
        self.assertEqual(result, 'hostname')

    def test_sanitize_very_long_hostname(self):
        """Test very long hostname truncated"""
        long_hostname = 'a' * 100
        result = sanitize_hostname(long_hostname)
        self.assertLessEqual(len(result), 64)

    def test_sanitize_custom_max_length(self):
        """Test custom max length"""
        long_hostname = 'a' * 50
        result = sanitize_hostname(long_hostname, max_length=30)
        self.assertLessEqual(len(result), 30)

    def test_sanitize_empty_result_fallback(self):
        """Test fallback to 'hifiberry' for empty result"""
        result = sanitize_hostname('!!!')
        self.assertEqual(result, 'hifiberry')

    def test_sanitize_only_hyphens_fallback(self):
        """Test fallback for input that becomes only hyphens"""
        result = sanitize_hostname('---')
        self.assertEqual(result, 'hifiberry')

    def test_sanitize_unicode_characters(self):
        """Test removing unicode characters"""
        result = sanitize_hostname('host-中文-name')
        self.assertNotIn('中文', result)

    def test_sanitize_hyphen_at_start_after_processing(self):
        """Test hyphen removal at start after processing"""
        result = sanitize_hostname('-my-host')
        self.assertFalse(result.startswith('-'))

    def test_sanitize_complex_example(self):
        """Test complex sanitization example"""
        result = sanitize_hostname('My-Cool!Host_123@')
        # Should be all lowercase, no special chars, valid
        self.assertTrue(all(c.islower() or c.isdigit() or c == '-' for c in result))
        self.assertTrue(validate_hostname(result))


class TestReadHostsFile(unittest.TestCase):
    """Test reading hosts file"""

    @patch('builtins.open', new_callable=mock_open, read_data='127.0.0.1\tlocalhost\n::1\t\tlocalhost\n')
    def test_read_hosts_file_success(self, mock_file):
        """Test successful hosts file reading"""
        result = read_hosts_file()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_read_hosts_file_not_found(self, mock_file):
        """Test reading non-existent hosts file"""
        result = read_hosts_file()
        self.assertEqual(result, [])

    @patch('builtins.open', side_effect=PermissionError())
    def test_read_hosts_file_permission_denied(self, mock_file):
        """Test reading hosts file with permission error"""
        result = read_hosts_file()
        self.assertEqual(result, [])

    @patch('builtins.open', side_effect=Exception('IO Error'))
    def test_read_hosts_file_generic_error(self, mock_file):
        """Test reading hosts file with generic error"""
        result = read_hosts_file()
        self.assertEqual(result, [])


class TestWriteHostsFile(unittest.TestCase):
    """Test writing hosts file"""

    @patch('builtins.open', new_callable=mock_open)
    def test_write_hosts_file_success(self, mock_file):
        """Test successful hosts file writing"""
        lines = ['127.0.0.1\tlocalhost\n', '::1\t\tlocalhost\n']
        result = write_hosts_file(lines)
        self.assertTrue(result)

    @patch('builtins.open', side_effect=PermissionError())
    def test_write_hosts_file_permission_denied(self, mock_file):
        """Test writing hosts file with permission error"""
        lines = ['127.0.0.1\tlocalhost\n']
        result = write_hosts_file(lines)
        self.assertFalse(result)

    @patch('builtins.open', side_effect=Exception('IO Error'))
    def test_write_hosts_file_generic_error(self, mock_file):
        """Test writing hosts file with generic error"""
        lines = ['127.0.0.1\tlocalhost\n']
        result = write_hosts_file(lines)
        self.assertFalse(result)


class TestUpdateHostsFile(unittest.TestCase):
    """Test updating hosts file"""

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_add_new_hostname(self, mock_write, mock_read):
        """Test adding new hostname to hosts file"""
        mock_read.return_value = [
            '127.0.0.1\tlocalhost\n',
            '::1\t\tlocalhost ip6-localhost\n'
        ]
        mock_write.return_value = True
        
        result = update_hosts_file(None, 'newhost')
        self.assertTrue(result)
        mock_write.assert_called_once()

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_remove_old_hostname(self, mock_write, mock_read):
        """Test removing old hostname from hosts file"""
        mock_read.return_value = [
            '127.0.0.1\tlocalhost oldhost\n',
            '::1\t\tlocalhost\n'
        ]
        mock_write.return_value = True
        
        result = update_hosts_file('oldhost', 'newhost')
        self.assertTrue(result)
        mock_write.assert_called_once()

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_empty_file(self, mock_write, mock_read):
        """Test updating empty hosts file creates new structure"""
        mock_read.return_value = []
        mock_write.return_value = True
        
        result = update_hosts_file(None, 'newhost')
        self.assertTrue(result)
        # Should have written with default structure
        mock_write.assert_called_once()

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_write_failure(self, mock_write, mock_read):
        """Test update fails when write fails"""
        mock_read.return_value = ['127.0.0.1\tlocalhost\n']
        mock_write.return_value = False
        
        result = update_hosts_file(None, 'newhost')
        self.assertFalse(result)

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_preserves_comments(self, mock_write, mock_read):
        """Test that comments in hosts file are preserved"""
        mock_read.return_value = [
            '# This is a comment\n',
            '127.0.0.1\tlocalhost\n'
        ]
        mock_write.return_value = True
        
        result = update_hosts_file(None, 'newhost')
        self.assertTrue(result)
        # Check that the written content preserves comments
        call_args = mock_write.call_args[0][0]
        self.assertTrue(any('# This is a comment' in line for line in call_args))


class TestGetCurrentHostname(unittest.TestCase):
    """Test getting current hostname"""

    @patch('subprocess.run')
    def test_get_current_hostname_success(self, mock_run):
        """Test successful hostname retrieval"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'myhostname\n'
        mock_run.return_value = mock_result
        
        result = get_current_hostname()
        self.assertEqual(result, 'myhostname')

    @patch('subprocess.run')
    def test_get_current_hostname_command_failure(self, mock_run):
        """Test hostname command failure"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = 'Command failed'
        mock_run.return_value = mock_result
        
        result = get_current_hostname()
        self.assertIsNone(result)

    @patch('subprocess.run', side_effect=Exception('Subprocess error'))
    def test_get_current_hostname_exception(self, mock_run):
        """Test hostname retrieval with exception"""
        result = get_current_hostname()
        self.assertIsNone(result)

    @patch('subprocess.run', side_effect=TimeoutError())
    def test_get_current_hostname_timeout(self, mock_run):
        """Test hostname retrieval timeout"""
        result = get_current_hostname()
        self.assertIsNone(result)


class TestSetHostnameWithHostsUpdate(unittest.TestCase):
    """Test setting hostname with hosts file update"""

    @patch('src.hostconfig.update_hosts_file')
    @patch('src.hostconfig.get_current_hostname')
    @patch('subprocess.run')
    def test_set_hostname_success(self, mock_run, mock_get, mock_update):
        """Test successful hostname setting"""
        mock_get.return_value = 'oldhost'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        mock_update.return_value = True
        
        result = set_hostname_with_hosts_update('newhost')
        self.assertTrue(result)

    @patch('src.hostconfig.get_current_hostname')
    @patch('subprocess.run')
    def test_set_hostname_command_failure(self, mock_run, mock_get):
        """Test hostname setting command failure"""
        mock_get.return_value = 'oldhost'
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = 'Command failed'
        mock_run.return_value = mock_result
        
        result = set_hostname_with_hosts_update('newhost')
        self.assertFalse(result)

    @patch('src.hostconfig.update_hosts_file')
    @patch('src.hostconfig.get_current_hostname')
    @patch('subprocess.run')
    def test_set_hostname_hosts_update_failure_not_critical(self, mock_run, mock_get, mock_update):
        """Test that hosts file update failure doesn't make function fail"""
        mock_get.return_value = 'oldhost'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        mock_update.return_value = False  # Hosts file update fails
        
        result = set_hostname_with_hosts_update('newhost')
        # Should still return True because hostname was set
        self.assertTrue(result)

    @patch('src.hostconfig.get_current_hostname', side_effect=Exception('Error'))
    def test_set_hostname_exception(self, mock_get):
        """Test hostname setting with exception"""
        result = set_hostname_with_hosts_update('newhost')
        self.assertFalse(result)


class TestMainCommandLine(unittest.TestCase):
    """Test main command-line interface"""

    @patch('src.hostconfig.get_current_hostname')
    @patch('sys.argv', ['hostconfig', 'get'])
    def test_main_get_command(self, mock_get):
        """Test main with 'get' command"""
        mock_get.return_value = 'myhostname'
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), 'myhostname')

    @patch('src.hostconfig.get_current_hostname')
    @patch('sys.argv', ['hostconfig', 'get'])
    def test_main_get_command_failure(self, mock_get):
        """Test main with 'get' command when it fails"""
        mock_get.return_value = None
        
        with patch('sys.stderr', new=StringIO()):
            result = main()
            self.assertEqual(result, 1)

    @patch('sys.argv', ['hostconfig', 'validate', 'validhost'])
    def test_main_validate_valid_hostname(self):
        """Test main with 'validate' command for valid hostname"""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertIn('valid', fake_out.getvalue())

    @patch('sys.argv', ['hostconfig', 'validate', 'hostname-'])
    def test_main_validate_invalid_hostname_parsed(self):
        """Test main with 'validate' command for invalid hostname"""
        # Use a hostname that ends with hyphen (invalid)
        with patch('sys.stderr', new=StringIO()):
            result = main()
            self.assertEqual(result, 1)

    @patch('sys.argv', ['hostconfig', 'sanitize', 'My-Host!'])
    def test_main_sanitize_command(self):
        """Test main with 'sanitize' command"""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            output = fake_out.getvalue().strip()
            # Should be lowercase without special chars
            self.assertTrue(validate_hostname(output))

    @patch('sys.argv', ['hostconfig', 'sanitize', 'VeryLongHostname', '--max-length', '10'])
    def test_main_sanitize_with_max_length(self):
        """Test main with 'sanitize' command and --max-length"""
        with patch('sys.stdout', new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue().strip()
            self.assertLessEqual(len(output), 10)

    @patch('src.hostconfig.set_hostname_with_hosts_update')
    @patch('sys.argv', ['hostconfig', 'set', 'newhost'])
    def test_main_set_command_valid(self, mock_set):
        """Test main with 'set' command for valid hostname"""
        mock_set.return_value = True
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertIn('Successfully set', fake_out.getvalue())

    @patch('sys.argv', ['hostconfig', 'set', 'hostname-'])
    def test_main_set_command_invalid_hostname_parsed(self):
        """Test main with 'set' command for invalid hostname"""
        # Use a hostname that ends with hyphen (invalid)
        with patch('sys.stderr', new=StringIO()):
            result = main()
            self.assertEqual(result, 1)

    @patch('src.hostconfig.set_hostname_with_hosts_update')
    @patch('sys.argv', ['hostconfig', 'set', 'newhost'])
    def test_main_set_command_failure(self, mock_set):
        """Test main with 'set' command when it fails"""
        mock_set.return_value = False
        
        with patch('sys.stderr', new=StringIO()):
            result = main()
            self.assertEqual(result, 1)

    @patch('sys.argv', ['hostconfig'])
    def test_main_no_command(self):
        """Test main with no command shows help"""
        with patch('sys.stdout', new=StringIO()):
            result = main()
            self.assertEqual(result, 0)


class TestEdgeCasesAndRobustness(unittest.TestCase):
    """Test edge cases and robustness"""

    def test_validate_hostname_with_dots(self):
        """Test hostname with dots (subdomain format)"""
        # Note: dots are not allowed in basic validation
        self.assertFalse(validate_hostname('host.example.com'))

    def test_sanitize_hostname_all_special_characters(self):
        """Test sanitizing string with only special characters"""
        result = sanitize_hostname('!@#$%^&*()')
        # Should fall back to 'hifiberry'
        self.assertEqual(result, 'hifiberry')

    def test_sanitize_hostname_numbers_only(self):
        """Test sanitizing numbers only"""
        result = sanitize_hostname('123456')
        self.assertEqual(result, '123456')
        self.assertTrue(validate_hostname(result))

    def test_validate_hostname_single_character(self):
        """Test single character hostname"""
        self.assertTrue(validate_hostname('a'))
        self.assertTrue(validate_hostname('1'))

    def test_sanitize_then_validate_round_trip(self):
        """Test that sanitized hostname always validates"""
        test_inputs = [
            'My-Host!@#',
            'UPPERCASE',
            'with-spaces',
            '!!!',
            'host_name',
            'short-name'
        ]
        
        for test_input in test_inputs:
            sanitized = sanitize_hostname(test_input)
            self.assertTrue(
                validate_hostname(sanitized),
                f"Sanitized '{test_input}' to '{sanitized}' which is invalid"
            )


class TestReturnTypes(unittest.TestCase):
    """Test return types and values"""

    def test_validate_hostname_returns_bool(self):
        """Test that validate_hostname returns bool"""
        result = validate_hostname('valid')
        self.assertIsInstance(result, bool)

    def test_sanitize_hostname_returns_str(self):
        """Test that sanitize_hostname returns str"""
        result = sanitize_hostname('test')
        self.assertIsInstance(result, str)

    @patch('src.hostconfig.read_hosts_file')
    @patch('src.hostconfig.write_hosts_file')
    def test_update_hosts_file_returns_bool(self, mock_write, mock_read):
        """Test that update_hosts_file returns bool"""
        mock_read.return_value = []
        mock_write.return_value = True
        result = update_hosts_file(None, 'test')
        self.assertIsInstance(result, bool)

    @patch('subprocess.run')
    def test_get_current_hostname_returns_optional_str(self, mock_run):
        """Test that get_current_hostname returns Optional[str]"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'host'
        mock_run.return_value = mock_result
        result = get_current_hostname()
        self.assertIsInstance(result, (str, type(None)))

    @patch('src.hostconfig.update_hosts_file')
    @patch('src.hostconfig.get_current_hostname')
    @patch('subprocess.run')
    def test_set_hostname_returns_bool(self, mock_run, mock_get, mock_update):
        """Test that set_hostname_with_hosts_update returns bool"""
        mock_get.return_value = 'old'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        mock_update.return_value = True
        result = set_hostname_with_hosts_update('new')
        self.assertIsInstance(result, bool)

    def test_main_returns_int(self):
        """Test that main returns int"""
        with patch('sys.argv', ['hostconfig']):
            result = main()
            self.assertIsInstance(result, int)


if __name__ == '__main__':
    unittest.main()
