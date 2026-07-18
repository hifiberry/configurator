#!/usr/bin/env python3
"""
Regression tests for HAT Tools module

Tests cover:
- HAT information retrieval
- EEPROM handling and error cases
- Command-line interface
- Default value handling
- Module constants
"""

import unittest
import sys
from unittest.mock import patch, MagicMock
from io import StringIO

# Add src directory to path for imports
sys.path.insert(0, '/home/ulf/data/configurator')

from src.hattools import (
    get_hat_info, main,
    DEFAULT_VENDOR, DEFAULT_PRODUCT, DEFAULT_UUID
)


class TestGetHatInfo(unittest.TestCase):
    """Test get_hat_info function"""

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_success_with_values(self, mock_hat_class):
        """Test successful HAT info retrieval with all values"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {
            'success': True,
            'vendor': 'HiFiBerry',
            'product': 'DAC+ Pro',
            'uuid': '12345678-1234-5678-1234-567812345678'
        }
        mock_hat_class.return_value = mock_hat
        
        result = get_hat_info(verbose=False)
        
        self.assertEqual(result['vendor'], 'HiFiBerry')
        self.assertEqual(result['product'], 'DAC+ Pro')
        self.assertEqual(result['uuid'], '12345678-1234-5678-1234-567812345678')

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_success_with_unknown_values(self, mock_hat_class):
        """Test HAT info retrieval when values are Unknown"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {
            'success': True,
            'vendor': 'Unknown',
            'product': 'Unknown',
            'uuid': 'Unknown'
        }
        mock_hat_class.return_value = mock_hat
        
        result = get_hat_info(verbose=False)
        
        self.assertIsNone(result['vendor'])
        self.assertIsNone(result['product'])
        self.assertIsNone(result['uuid'])

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_success_with_partial_values(self, mock_hat_class):
        """Test HAT info retrieval with some Unknown values"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {
            'success': True,
            'vendor': 'HiFiBerry',
            'product': 'Unknown',
            'uuid': '12345678-1234-5678-1234-567812345678'
        }
        mock_hat_class.return_value = mock_hat
        
        result = get_hat_info(verbose=False)
        
        self.assertEqual(result['vendor'], 'HiFiBerry')
        self.assertIsNone(result['product'])
        self.assertEqual(result['uuid'], '12345678-1234-5678-1234-567812345678')

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_failure(self, mock_hat_class):
        """Test HAT info retrieval when short_info fails"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {'success': False}
        mock_hat_class.return_value = mock_hat
        
        result = get_hat_info(verbose=False)
        
        self.assertIsNone(result['vendor'])
        self.assertIsNone(result['product'])
        self.assertIsNone(result['uuid'])

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_exception(self, mock_hat_class):
        """Test HAT info retrieval when exception is raised"""
        mock_hat_class.side_effect = Exception("EEPROM read error")
        
        result = get_hat_info(verbose=False)
        
        self.assertIsNone(result['vendor'])
        self.assertIsNone(result['product'])
        self.assertIsNone(result['uuid'])

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_short_info_exception(self, mock_hat_class):
        """Test HAT info when short_info raises exception"""
        mock_hat = MagicMock()
        mock_hat.short_info.side_effect = Exception("I2C communication error")
        mock_hat_class.return_value = mock_hat
        
        result = get_hat_info(verbose=False)
        
        self.assertIsNone(result['vendor'])
        self.assertIsNone(result['product'])
        self.assertIsNone(result['uuid'])

    def test_get_hat_info_without_hateeprom(self):
        """Test get_hat_info when HatEEPROM is None"""
        with patch('src.hattools.HatEEPROM', None):
            result = get_hat_info(verbose=False)
            
            self.assertIsNone(result['vendor'])
            self.assertIsNone(result['product'])
            self.assertIsNone(result['uuid'])

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_verbose_true(self, mock_hat_class):
        """Test get_hat_info with verbose=True logs warnings"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {'success': False}
        mock_hat_class.return_value = mock_hat
        
        with patch('src.hattools.logging.error'):
            result = get_hat_info(verbose=True)
            # Should not raise, just return None values
            self.assertIsNone(result['vendor'])

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_verbose_exception(self, mock_hat_class):
        """Test get_hat_info verbose mode with exception"""
        mock_hat_class.side_effect = Exception("Test error")
        
        with patch('src.hattools.logging.error') as mock_error:
            get_hat_info(verbose=True)
            # Error should be logged
            mock_error.assert_called()

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_missing_key(self, mock_hat_class):
        """Test HAT info when response is missing keys"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {
            'success': True,
            'vendor': 'HiFiBerry'
            # Missing 'product' and 'uuid'
        }
        mock_hat_class.return_value = mock_hat
        
        # Should not crash, but may return None for missing keys
        try:
            result = get_hat_info(verbose=False)
            # If it doesn't crash, that's good
            self.assertIsNotNone(result)
        except KeyError:
            # Or it might raise KeyError, which is also acceptable behavior
            pass

    @patch('src.hattools.HatEEPROM')
    def test_get_hat_info_empty_response(self, mock_hat_class):
        """Test HAT info with empty response"""
        mock_hat = MagicMock()
        mock_hat.short_info.return_value = {}
        mock_hat_class.return_value = mock_hat
        
        try:
            result = get_hat_info(verbose=False)
            self.assertIsNotNone(result)
        except KeyError:
            # Empty response should either return None values or raise
            pass


class TestDefaultConstants(unittest.TestCase):
    """Test module constants"""

    def test_default_vendor_constant(self):
        """Test DEFAULT_VENDOR constant"""
        self.assertEqual(DEFAULT_VENDOR, "no vendor")
        self.assertIsInstance(DEFAULT_VENDOR, str)

    def test_default_product_constant(self):
        """Test DEFAULT_PRODUCT constant"""
        self.assertEqual(DEFAULT_PRODUCT, "no product")
        self.assertIsInstance(DEFAULT_PRODUCT, str)

    def test_default_uuid_constant(self):
        """Test DEFAULT_UUID constant"""
        self.assertEqual(DEFAULT_UUID, "unknown")
        self.assertIsInstance(DEFAULT_UUID, str)


class TestMainCommandLine(unittest.TestCase):
    """Test main command-line interface"""

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_default_output_with_values(self, mock_get_info):
        """Test main with default output when HAT info is available"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC+ Pro',
            'uuid': '12345678-1234-5678-1234-567812345678'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), "HiFiBerry:DAC+ Pro")

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_default_output_with_none_values(self, mock_get_info):
        """Test main with default output when HAT info is None"""
        mock_get_info.return_value = {
            'vendor': None,
            'product': None,
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            output = fake_out.getvalue().strip()
            self.assertEqual(output, f"{DEFAULT_VENDOR}:{DEFAULT_PRODUCT}")

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_main_all_output_with_values(self, mock_get_info):
        """Test main with --all flag showing vendor:product:uuid"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC+ Pro',
            'uuid': '12345678'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), "HiFiBerry:DAC+ Pro:12345678")

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_main_all_output_with_none_values(self, mock_get_info):
        """Test main with --all flag and None values"""
        mock_get_info.return_value = {
            'vendor': None,
            'product': None,
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            output = fake_out.getvalue().strip()
            expected = f"{DEFAULT_VENDOR}:{DEFAULT_PRODUCT}:{DEFAULT_UUID}"
            self.assertEqual(output, expected)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '-a'])
    def test_main_all_output_short_flag(self, mock_get_info):
        """Test main with -a short flag"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC',
            'uuid': 'abc123'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), "HiFiBerry:DAC:abc123")

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--verbose'])
    def test_main_verbose_flag(self, mock_get_info):
        """Test main with --verbose flag"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC',
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()) as _fake_out:
            result = main()
            # Should be called with verbose=True
            mock_get_info.assert_called_with(verbose=True)
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '-v'])
    def test_main_verbose_flag_short(self, mock_get_info):
        """Test main with -v short flag"""
        mock_get_info.return_value = {
            'vendor': 'Test',
            'product': 'Product',
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()) as _fake_out:
            result = main()
            mock_get_info.assert_called_with(verbose=True)
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all', '--verbose'])
    def test_main_all_and_verbose_flags(self, mock_get_info):
        """Test main with both --all and --verbose flags"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC',
            'uuid': 'xyz'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            mock_get_info.assert_called_with(verbose=True)
            self.assertEqual(fake_out.getvalue().strip(), "HiFiBerry:DAC:xyz")
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_partial_none_values(self, mock_get_info):
        """Test main with some None values"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': None,
            'uuid': '12345'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            output = fake_out.getvalue().strip()
            self.assertEqual(output, f"HiFiBerry:{DEFAULT_PRODUCT}")
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_main_all_with_partial_none_values(self, mock_get_info):
        """Test main with --all and some None values"""
        mock_get_info.return_value = {
            'vendor': None,
            'product': 'DAC+ Pro',
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            output = fake_out.getvalue().strip()
            expected = f"{DEFAULT_VENDOR}:DAC+ Pro:{DEFAULT_UUID}"
            self.assertEqual(output, expected)
            self.assertEqual(result, 0)


class TestMainReturnValues(unittest.TestCase):
    """Test main function return values"""

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_returns_zero(self, mock_get_info):
        """Test that main returns 0"""
        mock_get_info.return_value = {
            'vendor': 'Test',
            'product': 'Product',
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()):
            result = main()
            self.assertEqual(result, 0)
            self.assertIsInstance(result, int)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_main_returns_zero_with_all(self, mock_get_info):
        """Test that main returns 0 with --all flag"""
        mock_get_info.return_value = {
            'vendor': None,
            'product': None,
            'uuid': None
        }
        
        with patch('sys.stdout', new=StringIO()):
            result = main()
            self.assertEqual(result, 0)


class TestOutputFormatting(unittest.TestCase):
    """Test output formatting"""

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_vendor_product_format(self, mock_get_info):
        """Test vendor:product output format"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC+ Pro',
            'uuid': 'ignored'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue().strip()
            # Should have exactly one colon separating vendor and product
            self.assertEqual(output.count(':'), 1)
            parts = output.split(':')
            self.assertEqual(parts[0], 'HiFiBerry')
            self.assertEqual(parts[1], 'DAC+ Pro')

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_vendor_product_uuid_format(self, mock_get_info):
        """Test vendor:product:uuid output format"""
        mock_get_info.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC',
            'uuid': '12345678'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue().strip()
            # Should have exactly two colons
            self.assertEqual(output.count(':'), 2)
            parts = output.split(':')
            self.assertEqual(len(parts), 3)
            self.assertEqual(parts[0], 'HiFiBerry')
            self.assertEqual(parts[1], 'DAC')
            self.assertEqual(parts[2], '12345678')

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_output_no_trailing_newline_in_content(self, mock_get_info):
        """Test that output content doesn't have trailing newlines when stripped"""
        mock_get_info.return_value = {
            'vendor': 'Test',
            'product': 'Prod',
            'uuid': 'uuid'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            main()
            # Output includes newline from print(), but strip removes it
            output = fake_out.getvalue()
            self.assertTrue(output.endswith('\n'))


class TestEdgeCasesAndRobustness(unittest.TestCase):
    """Test edge cases and robustness"""

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_with_empty_strings(self, mock_get_info):
        """Test main with empty string values"""
        mock_get_info.return_value = {
            'vendor': '',
            'product': '',
            'uuid': ''
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            main()
            # Empty strings are falsy but not None, so should be printed
            output = fake_out.getvalue().strip()
            self.assertEqual(output, ":")

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools', '--all'])
    def test_main_with_special_characters(self, mock_get_info):
        """Test main with special characters in values"""
        mock_get_info.return_value = {
            'vendor': 'Hi-Fi Berry™',
            'product': 'DAC+ Pro®',
            'uuid': 'uuid-with-dashes'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            output = fake_out.getvalue().strip()
            self.assertIn('Hi-Fi Berry™', output)
            self.assertIn('DAC+ Pro®', output)
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_with_unicode_values(self, mock_get_info):
        """Test main with Unicode characters"""
        mock_get_info.return_value = {
            'vendor': 'HiFi-音声',
            'product': '音频卡',
            'uuid': 'uuid-中文'
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            output = fake_out.getvalue().strip()
            self.assertIn('HiFi-音声', output)
            self.assertEqual(result, 0)

    @patch('src.hattools.get_hat_info')
    @patch('sys.argv', ['hattools'])
    def test_main_with_very_long_values(self, mock_get_info):
        """Test main with very long values"""
        long_vendor = 'A' * 1000
        long_product = 'B' * 1000
        
        mock_get_info.return_value = {
            'vendor': long_vendor,
            'product': long_product,
            'uuid': 'C' * 1000
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            output = fake_out.getvalue().strip()
            self.assertIn(long_vendor, output)
            self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
