"""
Comprehensive regression test suite for src/systeminfo module

Tests all system information collection functions including caching,
error handling, and data formatting.
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open

from src.systeminfo import SystemInfo


class TestSystemInfoInitialization(unittest.TestCase):
    """Tests for SystemInfo initialization"""

    def test_initialization(self):
        """Test SystemInfo object initialization"""
        info = SystemInfo()

        self.assertIsNone(info._pi_model)
        self.assertIsNone(info._hat_info)
        self.assertIsNone(info._system_uuid)
        self.assertIsNone(info._soundcard)
        self.assertIsNotNone(info.logger)

    def test_logger_name(self):
        """Test logger is correctly named"""
        info = SystemInfo()

        self.assertEqual(info.logger.name, "src.systeminfo")


class TestGetPiModelName(unittest.TestCase):
    """Tests for get_pi_model_name method"""

    @patch('src.systeminfo.PiModel')
    def test_get_pi_model_name_success(self, mock_pi_model_class):
        """Test successful Pi model name retrieval"""
        mock_instance = MagicMock()
        mock_instance.get_model_name.return_value = "Raspberry Pi 4 Model B\x00"
        mock_pi_model_class.return_value = mock_instance

        info = SystemInfo()
        result = info.get_pi_model_name()

        self.assertEqual(result, "Raspberry Pi 4 Model B")

    @patch('src.systeminfo.PiModel')
    def test_get_pi_model_name_error(self, mock_pi_model_class):
        """Test Pi model name retrieval error handling"""
        mock_pi_model_class.side_effect = Exception("PiModel error")

        info = SystemInfo()
        result = info.get_pi_model_name()

        self.assertEqual(result, "unknown")

    @patch('src.systeminfo.PiModel')
    def test_get_pi_model_name_caching(self, mock_pi_model_class):
        """Test Pi model is cached after first call"""
        mock_instance = MagicMock()
        mock_instance.get_model_name.return_value = "Raspberry Pi 3 Model B"
        mock_pi_model_class.return_value = mock_instance

        info = SystemInfo()
        result1 = info.get_pi_model_name()
        result2 = info.get_pi_model_name()

        self.assertEqual(result1, "Raspberry Pi 3 Model B")
        self.assertEqual(result2, "Raspberry Pi 3 Model B")
        mock_pi_model_class.assert_called_once()


class TestGetHatVendorCard(unittest.TestCase):
    """Tests for get_hat_vendor_card method"""

    @patch('src.systeminfo.get_hat_info')
    def test_get_hat_vendor_card_success(self, mock_get_hat):
        """Test successful HAT vendor card retrieval"""
        mock_get_hat.return_value = {
            'vendor': 'HiFiBerry',
            'product': 'DAC+ Standard'
        }

        info = SystemInfo()
        result = info.get_hat_vendor_card()

        self.assertEqual(result, "HiFiBerry:DAC+ Standard")

    @patch('src.systeminfo.get_hat_info')
    def test_get_hat_vendor_card_none_values(self, mock_get_hat):
        """Test HAT vendor card with None values"""
        mock_get_hat.return_value = {'vendor': None, 'product': None}

        info = SystemInfo()
        result = info.get_hat_vendor_card()

        self.assertEqual(result, "unknown:unknown")

    @patch('src.systeminfo.get_hat_info')
    def test_get_hat_vendor_card_missing_keys(self, mock_get_hat):
        """Test HAT vendor card with missing keys"""
        mock_get_hat.return_value = {}

        info = SystemInfo()
        result = info.get_hat_vendor_card()

        self.assertEqual(result, "unknown:unknown")

    @patch('src.systeminfo.get_hat_info')
    def test_get_hat_vendor_card_error(self, mock_get_hat):
        """Test HAT vendor card retrieval error handling"""
        mock_get_hat.side_effect = Exception("HAT error")

        info = SystemInfo()
        result = info.get_hat_vendor_card()

        self.assertEqual(result, "unknown:unknown")


class TestGetSystemUuid(unittest.TestCase):
    """Tests for get_system_uuid method"""

    @patch('builtins.open', new_callable=mock_open, read_data="12345678-1234-1234-1234-123456789012\n")
    def test_get_system_uuid_success(self, mock_file):
        """Test successful system UUID retrieval"""
        info = SystemInfo()
        result = info.get_system_uuid()

        self.assertEqual(result, "12345678-1234-1234-1234-123456789012")
        mock_file.assert_called_once_with("/etc/uuid", "r")

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_get_system_uuid_file_not_found(self, mock_file):
        """Test system UUID when file not found"""
        info = SystemInfo()
        result = info.get_system_uuid()

        self.assertIsNone(result)

    @patch('builtins.open', side_effect=PermissionError)
    def test_get_system_uuid_permission_denied(self, mock_file):
        """Test system UUID when permission denied"""
        info = SystemInfo()
        result = info.get_system_uuid()

        self.assertIsNone(result)

    @patch('builtins.open', new_callable=mock_open, read_data="uuid-with-spaces   \n")
    def test_get_system_uuid_strips_whitespace(self, mock_file):
        """Test system UUID whitespace stripping"""
        info = SystemInfo()
        result = info.get_system_uuid()

        self.assertEqual(result, "uuid-with-spaces")


class TestGetHostnames(unittest.TestCase):
    """Tests for get_hostnames method"""

    @patch('src.systeminfo.get_hostnames_with_fallback')
    def test_get_hostnames_success(self, mock_get_hostnames):
        """Test successful hostname retrieval"""
        mock_get_hostnames.return_value = ("myhost", "My Pretty Host")

        info = SystemInfo()
        result = info.get_hostnames()

        self.assertEqual(result, ("myhost", "My Pretty Host"))

    @patch('src.systeminfo.get_hostnames_with_fallback')
    def test_get_hostnames_none_values(self, mock_get_hostnames):
        """Test hostname retrieval with None values"""
        mock_get_hostnames.return_value = (None, None)

        info = SystemInfo()
        result = info.get_hostnames()

        self.assertEqual(result, (None, None))

    @patch('src.systeminfo.get_hostnames_with_fallback')
    def test_get_hostnames_error(self, mock_get_hostnames):
        """Test hostname retrieval error handling"""
        mock_get_hostnames.side_effect = Exception("Hostname error")

        info = SystemInfo()
        result = info.get_hostnames()

        self.assertEqual(result, (None, None))


class TestGetSoundcardInfo(unittest.TestCase):
    """Tests for get_soundcard_info method"""

    @patch('src.systeminfo.SystemInfo._is_soundcard_fixed_in_config_txt')
    @patch('src.systeminfo.SystemInfo._get_soundcard_pin_source')
    @patch('src.systeminfo.SystemInfo._get_soundcard')
    def test_get_soundcard_info_success(self, mock_get_soundcard, mock_pin_source, mock_fixed):
        """Test successful soundcard info retrieval"""
        mock_soundcard = MagicMock()
        mock_soundcard.name = "HiFiBerry DAC+"
        mock_soundcard.volume_control = "Digital"
        mock_soundcard.headphone_volume_control = None
        mock_soundcard.get_hardware_index.return_value = 0
        mock_soundcard.output_channels = 2
        mock_soundcard.input_channels = 0
        mock_soundcard.features = ["DSP"]
        mock_soundcard.hat_name = "DAC+"
        mock_soundcard.supports_dsp = True
        mock_soundcard.card_type = ["DAC", "DSP"]
        mock_get_soundcard.return_value = mock_soundcard
        mock_fixed.return_value = False
        mock_pin_source.return_value = None

        info = SystemInfo()
        result = info.get_soundcard_info()

        self.assertEqual(result['name'], "HiFiBerry DAC+")
        self.assertEqual(result['volume_control'], "Digital")
        self.assertIsNone(result['headphone_volume_control'])
        self.assertEqual(result['hardware_index'], 0)
        self.assertEqual(result['output_channels'], 2)
        self.assertFalse(result['fixedInConfigTxt'])
        self.assertIsNone(result['pinSource'])

    @patch('src.systeminfo.SystemInfo._get_soundcard')
    def test_get_soundcard_info_error(self, mock_get_soundcard):
        """Test soundcard info error handling"""
        mock_get_soundcard.side_effect = Exception("Soundcard error")

        info = SystemInfo()
        result = info.get_soundcard_info()

        self.assertEqual(result['name'], 'unknown')
        self.assertIsNone(result['volume_control'])
        self.assertIsNone(result['hardware_index'])
        self.assertEqual(result['output_channels'], 0)


class TestGetSystemInfoDict(unittest.TestCase):
    """Tests for get_system_info_dict method"""

    @patch('src.systeminfo.SystemInfo._get_memory_info')
    @patch('src.systeminfo.SystemInfo._get_hostname_info')
    @patch('src.systeminfo.SystemInfo.get_soundcard_info')
    @patch('src.systeminfo.SystemInfo._get_system_uuid')
    @patch('src.systeminfo.SystemInfo._get_hat_info')
    @patch('src.systeminfo.SystemInfo._get_pi_model')
    def test_get_system_info_dict_success(self, mock_pi, mock_hat, mock_uuid,
                                          mock_soundcard, mock_hostname, mock_memory):
        """Test successful system info dict retrieval"""
        mock_pi.return_value = MagicMock(get_model_name=lambda: "Pi 4\x00", version="1.2")
        mock_hat.return_value = {'vendor': 'HiFiBerry', 'product': 'DAC+', 'uuid': 'hat-uuid'}
        mock_uuid.return_value = "sys-uuid-123"
        mock_soundcard.return_value = {'name': 'DAC+', 'volume_control': 'Digital'}
        mock_hostname.return_value = ('myhost', 'My Host')
        mock_memory.return_value = {'total_gb': 4, 'total_mb': 4096, 'total_kb': 4194304}

        info = SystemInfo()
        result = info.get_system_info_dict()

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['pi_model']['name'], 'Pi 4')
        self.assertEqual(result['hat_info']['vendor'], 'HiFiBerry')
        self.assertEqual(result['system']['uuid'], 'sys-uuid-123')
        self.assertEqual(result['soundcard']['name'], 'DAC+')

    @patch('src.systeminfo.SystemInfo._get_pi_model')
    def test_get_system_info_dict_error(self, mock_pi):
        """Test system info dict error handling"""
        mock_pi.side_effect = Exception("Error")

        info = SystemInfo()
        result = info.get_system_info_dict()

        self.assertEqual(result['status'], 'error')
        self.assertIn('error', result)


class TestGetFlatInfoDict(unittest.TestCase):
    """Tests for get_flat_info_dict method"""

    @patch('src.systeminfo.SystemInfo._get_memory_info')
    @patch('src.systeminfo.SystemInfo._get_hostname_info')
    @patch('src.systeminfo.SystemInfo.get_soundcard_info')
    @patch('src.systeminfo.SystemInfo._get_system_uuid')
    @patch('src.systeminfo.SystemInfo._get_hat_info')
    @patch('src.systeminfo.SystemInfo._get_pi_model')
    def test_get_flat_info_dict_success(self, mock_pi, mock_hat, mock_uuid,
                                        mock_soundcard, mock_hostname, mock_memory):
        """Test successful flat info dict retrieval"""
        mock_pi.return_value = MagicMock(get_model_name=lambda: "Pi 4\x00", version="1.2")
        mock_hat.return_value = {'vendor': 'HiFiBerry', 'product': 'DAC+'}
        mock_uuid.return_value = "sys-uuid-123"
        mock_soundcard.return_value = {'name': 'DAC+'}
        mock_hostname.return_value = ('myhost', 'My Host')
        mock_memory.return_value = {'total_gb': 4, 'total_mb': 4096}

        info = SystemInfo()
        result = info.get_flat_info_dict()

        self.assertEqual(result['Pi Model'], 'Pi 4 1.2')
        self.assertEqual(result['Memory'], '4 GB (4096 MB)')
        self.assertEqual(result['HAT'], 'HiFiBerry DAC+')
        self.assertEqual(result['Sound Card'], 'DAC+')
        self.assertEqual(result['UUID'], 'sys-uuid-123')
        self.assertEqual(result['Hostname'], 'myhost')

    @patch('src.systeminfo.SystemInfo._get_memory_info')
    @patch('src.systeminfo.SystemInfo._get_hostname_info')
    @patch('src.systeminfo.SystemInfo.get_soundcard_info')
    @patch('src.systeminfo.SystemInfo._get_system_uuid')
    @patch('src.systeminfo.SystemInfo._get_hat_info')
    @patch('src.systeminfo.SystemInfo._get_pi_model')
    def test_get_flat_info_dict_with_none_values(self, mock_pi, mock_hat, mock_uuid,
                                                   mock_soundcard, mock_hostname, mock_memory):
        """Test flat info dict with None values"""
        mock_pi.return_value = MagicMock(get_model_name=lambda: "Pi 4", version='unknown')
        mock_hat.return_value = {'vendor': None, 'product': None}
        mock_uuid.return_value = None
        mock_soundcard.return_value = {'name': 'unknown'}
        mock_hostname.return_value = (None, None)
        mock_memory.return_value = {}

        info = SystemInfo()
        result = info.get_flat_info_dict()

        self.assertEqual(result['Pi Model'], 'Pi 4')
        self.assertEqual(result['Memory'], 'unknown')
        self.assertEqual(result['HAT'], 'unknown unknown')
        self.assertEqual(result['UUID'], 'unknown')
        self.assertEqual(result['Hostname'], 'unknown')

    @patch('src.systeminfo.SystemInfo._get_pi_model')
    def test_get_flat_info_dict_error(self, mock_pi):
        """Test flat info dict error handling"""
        mock_pi.side_effect = Exception("Error")

        info = SystemInfo()
        result = info.get_flat_info_dict()

        self.assertEqual(result['Pi Model'], 'unknown')
        self.assertEqual(result['Sound Card'], 'unknown')


class TestGetSimpleOutput(unittest.TestCase):
    """Tests for get_simple_output method"""

    @patch('src.systeminfo.SystemInfo.get_system_uuid')
    @patch('src.systeminfo.SystemInfo.get_soundcard_info')
    @patch('src.systeminfo.SystemInfo.get_hat_vendor_card')
    @patch('src.systeminfo.SystemInfo.get_pi_model_name')
    def test_get_simple_output_with_uuid(self, mock_pi_name, mock_hat,
                                         mock_soundcard, mock_uuid):
        """Test simple output with all fields"""
        mock_pi_name.return_value = "Raspberry Pi 4 Model B"
        mock_hat.return_value = "HiFiBerry:DAC+"
        mock_soundcard.return_value = {'name': 'HiFiBerry DAC+'}
        mock_uuid.return_value = "12345678-1234-1234-1234-123456789012"

        info = SystemInfo()
        result = info.get_simple_output()

        self.assertIn("Pi Model: Raspberry Pi 4 Model B", result)
        self.assertIn("Hat info: HiFiBerry:DAC+", result)
        self.assertIn("Sound Card: HiFiBerry DAC+", result)
        self.assertIn("System UUID: 12345678-1234-1234-1234-123456789012", result)

    @patch('src.systeminfo.SystemInfo.get_system_uuid')
    @patch('src.systeminfo.SystemInfo.get_soundcard_info')
    @patch('src.systeminfo.SystemInfo.get_hat_vendor_card')
    @patch('src.systeminfo.SystemInfo.get_pi_model_name')
    def test_get_simple_output_without_uuid(self, mock_pi_name, mock_hat,
                                            mock_soundcard, mock_uuid):
        """Test simple output without UUID"""
        mock_pi_name.return_value = "Raspberry Pi 3 Model B"
        mock_hat.return_value = "unknown:unknown"
        mock_soundcard.return_value = {'name': 'unknown'}
        mock_uuid.return_value = None

        info = SystemInfo()
        result = info.get_simple_output()

        self.assertIn("Pi Model: Raspberry Pi 3 Model B", result)
        self.assertNotIn("System UUID:", result)


class TestPrintSimpleOutput(unittest.TestCase):
    """Tests for print_simple_output method"""

    @patch('builtins.print')
    @patch('src.systeminfo.SystemInfo.get_simple_output')
    def test_print_simple_output(self, mock_get_output, mock_print):
        """Test print simple output"""
        mock_get_output.return_value = "Test output"

        info = SystemInfo()
        info.print_simple_output()

        mock_print.assert_called_once_with("Test output")


class TestCaching(unittest.TestCase):
    """Tests for caching behavior"""

    @patch('src.systeminfo.PiModel')
    def test_pi_model_caching(self, mock_pi_model_class):
        """Test Pi model caching across calls"""
        mock_instance = MagicMock()
        mock_pi_model_class.return_value = mock_instance

        info = SystemInfo()
        result1 = info._get_pi_model()
        result2 = info._get_pi_model()

        self.assertIs(result1, result2)
        mock_pi_model_class.assert_called_once()

    @patch('src.systeminfo.get_hat_info')
    def test_hat_info_caching(self, mock_get_hat):
        """Test HAT info caching across calls"""
        mock_get_hat.return_value = {'vendor': 'HiFiBerry'}

        info = SystemInfo()
        result1 = info._get_hat_info()
        result2 = info._get_hat_info()

        self.assertEqual(result1, result2)
        mock_get_hat.assert_called_once()

    @patch('builtins.open', new_callable=mock_open, read_data="uuid-123\n")
    def test_uuid_caching(self, mock_file):
        """Test UUID caching across calls"""
        info = SystemInfo()
        result1 = info._get_system_uuid()
        result2 = info._get_system_uuid()

        self.assertEqual(result1, result2)
        mock_file.assert_called_once()

    @patch('src.systeminfo.Soundcard')
    def test_soundcard_caching(self, mock_soundcard_class):
        """Test soundcard caching across calls"""
        mock_instance = MagicMock()
        mock_soundcard_class.return_value = mock_instance

        info = SystemInfo()
        result1 = info._get_soundcard()
        result2 = info._get_soundcard()

        self.assertIs(result1, result2)
        mock_soundcard_class.assert_called_once()

    @patch('src.systeminfo.Soundcard')
    def test_soundcard_no_cache_when_prioritize_aplay(self, mock_soundcard_class):
        """Test soundcard caching is bypassed when prioritize_aplay is True"""
        mock_instance = MagicMock()
        mock_soundcard_class.return_value = mock_instance

        info = SystemInfo()
        info._get_soundcard(prioritize_aplay=False)
        info._get_soundcard(prioritize_aplay=True)

        # Should create a new instance due to prioritize_aplay=True
        self.assertEqual(mock_soundcard_class.call_count, 2)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling across methods"""

    @patch('src.systeminfo.SystemInfo._get_pi_model')
    @patch('src.systeminfo.SystemInfo._get_hat_info')
    @patch('src.systeminfo.SystemInfo._get_system_uuid')
    def test_graceful_error_in_system_info(self, mock_uuid, mock_hat, mock_pi):
        """Test graceful error handling in system info collection"""
        mock_pi.side_effect = Exception("PI error")
        mock_hat.return_value = {'vendor': 'Test'}
        mock_uuid.return_value = None

        info = SystemInfo()
        result = info.get_system_info_dict()

        # Should still return a dict with error status
        self.assertEqual(result['status'], 'error')
        self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
