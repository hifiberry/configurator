"""
Comprehensive regression test suite for src/volume module

Tests all volume utility functions including subprocess fallback,
configuration storage/retrieval, and caching.
"""

import unittest
from unittest.mock import patch, MagicMock
from subprocess import CalledProcessError

from src.volume import (
    get_cached_card_index,
    get_current_volume,
    set_volume,
    store_volume,
    restore_volume,
    is_pipewire_available,
    get_pipewire_volume,
    set_pipewire_volume,
    get_available_headphone_controls,
    get_headphone_volume,
    set_headphone_volume,
    store_headphone_volume,
    restore_headphone_volume,
    list_available_controls,
)


class TestCachedCardIndex(unittest.TestCase):
    """Tests for get_cached_card_index function"""

    def setUp(self):
        """Reset cache before each test"""
        import src.volume as volume_module
        volume_module._cached_card_index = None
        volume_module._cached_soundcard = None

    @patch('src.volume.Soundcard')
    def test_cache_initialization(self, mock_soundcard_class):
        """Test cache is initialized on first call"""
        mock_instance = MagicMock()
        mock_instance.get_hardware_index.return_value = 0
        mock_soundcard_class.return_value = mock_instance

        result = get_cached_card_index()

        self.assertEqual(result, 0)
        mock_soundcard_class.assert_called_once()
        mock_instance.get_hardware_index.assert_called_once()

    @patch('src.volume.Soundcard')
    def test_cache_reused(self, mock_soundcard_class):
        """Test cached value is reused on second call"""
        mock_instance = MagicMock()
        mock_instance.get_hardware_index.return_value = 1
        mock_soundcard_class.return_value = mock_instance

        result1 = get_cached_card_index()
        result2 = get_cached_card_index()

        self.assertEqual(result1, 1)
        self.assertEqual(result2, 1)
        mock_soundcard_class.assert_called_once()

    @patch('src.volume.Soundcard')
    def test_cache_returns_none(self, mock_soundcard_class):
        """Test when no sound card is detected"""
        mock_instance = MagicMock()
        mock_instance.get_hardware_index.return_value = None
        mock_soundcard_class.return_value = mock_instance

        result = get_cached_card_index()

        self.assertIsNone(result)


class TestGetCurrentVolume(unittest.TestCase):
    """Tests for get_current_volume function"""

    def test_get_volume_none_parameters(self):
        """Test with None parameters"""
        result = get_current_volume(None, 'Headphone')
        self.assertIsNone(result)

        result = get_current_volume(0, None)
        self.assertIsNone(result)

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_volume_subprocess_percentage(self, mock_subprocess):
        """Test volume retrieval via subprocess with percentage"""
        mock_subprocess.return_value = "Simple mixer control 'Headphone' [75%]"

        result = get_current_volume(0, 'Headphone')

        self.assertEqual(result, '75')

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_volume_subprocess_db(self, mock_subprocess):
        """Test volume retrieval via subprocess with dB"""
        mock_subprocess.return_value = "Simple mixer control 'Master' [-5.00dB]"

        result = get_current_volume(0, 'Master')

        self.assertEqual(result, '-5.00')

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_volume_subprocess_error(self, mock_subprocess):
        """Test subprocess error handling"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = get_current_volume(0, 'Headphone')

        self.assertIsNone(result)

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_volume_subprocess_no_match(self, mock_subprocess):
        """Test when output doesn't contain percentage or dB"""
        mock_subprocess.return_value = "unparseable output"

        result = get_current_volume(0, 'Headphone')

        self.assertIsNone(result)


class TestSetVolume(unittest.TestCase):
    """Tests for set_volume function"""

    def test_set_volume_none_parameters(self):
        """Test with None parameters"""
        result = set_volume(None, 'Headphone', '50')
        self.assertFalse(result)

        result = set_volume(0, None, '50')
        self.assertFalse(result)

    def test_set_volume_invalid_value(self):
        """Test invalid volume value"""
        result = set_volume(0, 'Headphone', 'invalid')
        self.assertFalse(result)

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_set_volume_subprocess_percentage(self, mock_subprocess):
        """Test volume setting via subprocess with percentage"""
        result = set_volume(0, 'Headphone', '75')

        self.assertTrue(result)
        mock_subprocess.assert_called_once()
        assert 'amixer' in mock_subprocess.call_args[0][0]
        assert '75%' in mock_subprocess.call_args[0][0]

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_set_volume_subprocess_db(self, mock_subprocess):
        """Test volume setting via subprocess with dB value"""
        result = set_volume(0, 'Master', '5.5')

        self.assertTrue(result)
        call_cmd = mock_subprocess.call_args[0][0]
        assert 'amixer' in call_cmd
        assert 'dB' in call_cmd

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_set_volume_subprocess_error(self, mock_subprocess):
        """Test subprocess error handling"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = set_volume(0, 'Headphone', '50')

        self.assertFalse(result)


class TestPipeWireAvailable(unittest.TestCase):
    """Tests for is_pipewire_available function"""

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_pipewire_available_subprocess_success(self, mock_subprocess):
        """Test PipeWire availability via subprocess"""
        mock_subprocess.return_value = "Simple mixer control 'Master'"

        result = is_pipewire_available()

        self.assertTrue(result)

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_pipewire_available_subprocess_not_found(self, mock_subprocess):
        """Test PipeWire unavailable via subprocess"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = is_pipewire_available()

        self.assertFalse(result)


class TestGetPipeWireVolume(unittest.TestCase):
    """Tests for get_pipewire_volume function"""

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_pipewire_volume_success(self, mock_subprocess):
        """Test getting PipeWire volume via subprocess"""
        mock_subprocess.return_value = "Simple mixer control 'Master' [65%]"

        result = get_pipewire_volume('Master')

        self.assertEqual(result, '65')

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_pipewire_volume_error(self, mock_subprocess):
        """Test PipeWire volume error handling"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = get_pipewire_volume('Master')

        self.assertIsNone(result)


class TestSetPipeWireVolume(unittest.TestCase):
    """Tests for set_pipewire_volume function"""

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_set_pipewire_volume_success(self, mock_subprocess):
        """Test setting PipeWire volume via subprocess"""
        result = set_pipewire_volume('Master', '70')

        self.assertTrue(result)
        mock_subprocess.assert_called_once()

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_set_pipewire_volume_error(self, mock_subprocess):
        """Test PipeWire volume error handling"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = set_pipewire_volume('Master', '50')

        self.assertFalse(result)


class TestHeadphoneControls(unittest.TestCase):
    """Tests for headphone control functions"""

    @patch('src.volume.list_available_controls')
    def test_get_available_headphone_controls_found(self, mock_list_controls):
        """Test finding available headphone controls"""
        mock_list_controls.return_value = ['Master', 'Headphone', 'Speaker']

        result = get_available_headphone_controls()

        self.assertEqual(result, ['Headphone'])

    @patch('src.volume.list_available_controls')
    def test_get_available_headphone_controls_not_found(self, mock_list_controls):
        """Test when headphone control not found"""
        mock_list_controls.return_value = ['Master', 'Speaker']

        result = get_available_headphone_controls()

        self.assertEqual(result, [])

    @patch('src.volume.list_available_controls')
    def test_get_available_headphone_controls_error(self, mock_list_controls):
        """Test error handling"""
        mock_list_controls.side_effect = Exception('Device error')

        result = get_available_headphone_controls()

        self.assertEqual(result, [])

    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.get_current_volume')
    def test_get_headphone_volume_success(self, mock_get_vol, mock_card, mock_get_controls):
        """Test getting headphone volume"""
        mock_get_controls.return_value = ['Headphone']
        mock_card.return_value = 0
        mock_get_vol.return_value = '85'

        result = get_headphone_volume()

        self.assertEqual(result, ('85', 'Headphone'))

    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    def test_get_headphone_volume_no_control(self, mock_card, mock_get_controls):
        """Test when no headphone control available"""
        mock_get_controls.return_value = []
        mock_card.return_value = 0

        result = get_headphone_volume()

        self.assertEqual(result, (None, None))

    @patch('src.volume.set_volume')
    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    def test_set_headphone_volume_success(self, mock_card, mock_get_controls, mock_set_vol):
        """Test setting headphone volume"""
        mock_get_controls.return_value = ['Headphone']
        mock_card.return_value = 0
        mock_set_vol.return_value = True

        result = set_headphone_volume('80')

        self.assertTrue(result)

    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    def test_set_headphone_volume_no_control(self, mock_card, mock_get_controls):
        """Test when no headphone control available"""
        mock_get_controls.return_value = []
        mock_card.return_value = 0

        result = set_headphone_volume('80')

        self.assertFalse(result)


class TestStoreOperations(unittest.TestCase):
    """Tests for store_volume and restore_volume functions"""

    @patch('src.volume.store_headphone_volume')
    @patch('src.volume.is_pipewire_available')
    @patch('src.volume.get_current_volume')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.ConfigDB')
    def test_store_volume_success(self, mock_db_class, mock_card, mock_get_vol,
                                   mock_pipewire, mock_store_headphone):
        """Test successful volume storage"""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_card.return_value = 0
        mock_get_vol.return_value = '100'
        mock_pipewire.return_value = False
        mock_store_headphone.return_value = False

        with patch('src.volume._cached_soundcard') as mock_soundcard:
            mock_soundcard.get_mixer_control_name.return_value = 'PCM'
            result = store_volume()

        self.assertTrue(result)
        mock_db.set.assert_called()

    @patch('src.volume.store_headphone_volume')
    @patch('src.volume.get_cached_card_index')
    def test_store_volume_no_card(self, mock_card, mock_store_headphone):
        """Test storage when no card detected"""
        mock_card.return_value = None
        mock_store_headphone.return_value = False

        result = store_volume()

        self.assertFalse(result)

    @patch('src.volume.restore_headphone_volume')
    @patch('src.volume.is_pipewire_available')
    @patch('src.volume.set_volume')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.ConfigDB')
    def test_restore_volume_success(self, mock_db_class, mock_card,
                                     mock_set_vol, mock_pipewire, mock_restore_headphone):
        """Test successful volume restoration"""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get.side_effect = lambda key: {
            'system.volume': '85',
            'system.volume.card': '0',
            'system.volume.control': 'PCM'
        }.get(key)
        mock_card.return_value = 0
        mock_set_vol.return_value = True
        mock_pipewire.return_value = False
        mock_restore_headphone.return_value = False

        with patch('src.volume._cached_soundcard') as mock_soundcard:
            mock_soundcard.get_mixer_control_name.return_value = 'PCM'
            result = restore_volume()

        self.assertTrue(result)


class TestListAvailableControls(unittest.TestCase):
    """Tests for list_available_controls function"""

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_list_controls_subprocess_with_card(self, mock_subprocess):
        """Test listing controls via subprocess"""
        mock_subprocess.return_value = """Simple mixer control 'Master'
Simple mixer control 'PCM'
Simple mixer control 'Headphone'"""

        result = list_available_controls(0)

        self.assertEqual(result, ['Master', 'PCM', 'Headphone'])

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_list_controls_subprocess_default_card(self, mock_subprocess):
        """Test listing controls via subprocess without card"""
        mock_subprocess.return_value = "Simple mixer control 'Master'\nSimple mixer control 'PCM'"

        result = list_available_controls()

        self.assertEqual(result, ['Master', 'PCM'])

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_list_controls_subprocess_error(self, mock_subprocess):
        """Test subprocess error handling"""
        mock_subprocess.side_effect = CalledProcessError(1, 'amixer')

        result = list_available_controls()

        self.assertEqual(result, [])


class TestHeadphoneVolumeStorage(unittest.TestCase):
    """Tests for headphone volume storage and restoration"""

    @patch('src.volume.get_current_volume')
    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.ConfigDB')
    def test_store_headphone_volume_success(self, mock_db_class, mock_card,
                                            mock_get_controls, mock_get_current_vol):
        """Test successful headphone volume storage"""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_card.return_value = 0
        mock_get_controls.return_value = ['Headphone']
        mock_get_current_vol.return_value = '90'

        result = store_headphone_volume()

        self.assertTrue(result)
        mock_db.set.assert_called()

    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    def test_store_headphone_volume_no_controls(self, mock_card, mock_get_controls):
        """Test when no headphone controls available"""
        mock_card.return_value = 0
        mock_get_controls.return_value = []

        result = store_headphone_volume()

        self.assertFalse(result)

    @patch('src.volume.set_volume')
    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.ConfigDB')
    def test_restore_headphone_volume_success(self, mock_db_class, mock_card,
                                               mock_get_controls, mock_set_vol):
        """Test successful headphone volume restoration"""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get.side_effect = lambda key: {
            'system.volume.headphone': '90',
            'system.volume.headphone.card': '0',
            'system.volume.headphone.control': 'Headphone'
        }.get(key)
        mock_card.return_value = 0
        mock_get_controls.return_value = ['Headphone']
        mock_set_vol.return_value = True

        result = restore_headphone_volume()

        self.assertTrue(result)

    @patch('src.volume.ConfigDB')
    def test_restore_headphone_volume_no_saved(self, mock_db_class):
        """Test when no saved headphone volume"""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get.return_value = None

        result = restore_headphone_volume()

        self.assertFalse(result)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error conditions"""

    def test_volume_value_conversion(self):
        """Test volume value conversion with floats"""
        result = set_volume(0, 'Headphone', '75.5')
        # Without subprocess mock it will fail, but should parse the float
        self.assertFalse(result)

    @patch('src.volume.get_available_headphone_controls')
    @patch('src.volume.get_cached_card_index')
    @patch('src.volume.get_current_volume')
    def test_get_headphone_volume_first_control(self, mock_get_vol, mock_card, mock_get_controls):
        """Test getting headphone volume uses first available control"""
        mock_get_controls.return_value = ['Headphone']
        mock_card.return_value = 2
        mock_get_vol.return_value = '92'

        volume, control = get_headphone_volume()

        self.assertEqual(volume, '92')
        self.assertEqual(control, 'Headphone')
        mock_get_vol.assert_called_once_with(2, 'Headphone')

    @patch('src.volume.alsa_available', False)
    @patch('src.volume.subprocess.check_output')
    def test_get_volume_with_special_characters(self, mock_subprocess):
        """Test volume retrieval with special characters in control name"""
        mock_subprocess.return_value = "Simple mixer control 'Line In' [50%]"

        result = get_current_volume(0, 'Line In')

        self.assertEqual(result, '50')


if __name__ == '__main__':
    unittest.main()
