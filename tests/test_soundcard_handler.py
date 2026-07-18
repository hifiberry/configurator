"""
Comprehensive regression test suite for SoundcardHandler

Tests all public methods and error handling paths to ensure sound card
configuration API endpoints work correctly.
"""

import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys

# Mock Flask before importing handler
flask_mock = MagicMock()


def mock_jsonify(data):
    """Mock jsonify that returns the data dict directly for testing"""
    return data


class MockResponse:
    """Mock Flask Response class for testing"""

    def __init__(self, json_data=None, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def __iter__(self):
        """Support tuple unpacking for (response, status_code)"""
        return iter([self, self.status_code])


flask_mock.jsonify = mock_jsonify
flask_mock.Response = MockResponse
flask_mock.request = MagicMock()
sys.modules['flask'] = flask_mock

from src.handlers.soundcard_handler import SoundcardHandler  # noqa: E402


def get_response(result):
    """Helper to extract response and status code from handler result"""
    if isinstance(result, tuple):
        response, status = result[0], result[1]
    else:
        response, status = result, 200

    # Normalize Response-like objects from other test Flask mocks.
    if hasattr(response, 'get_json'):
        json_payload = response.get_json()
        if json_payload is not None:
            response = json_payload

    return response, status


class TestSoundcardHandlerListSoundcards(unittest.TestCase):
    """Tests for list_soundcards endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'},
        'hifiberry-dac': {'dtoverlay': 'hifiberry-dac'}
    })
    def test_list_soundcards_success(self):
        """Test successful listing of sound cards"""
        result, status = get_response(self.handler.handle_list_soundcards())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertIn('data', result)
        self.assertIn('soundcards', result['data'])
        self.assertEqual(result['data']['count'], 2)

    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {})
    def test_list_soundcards_empty(self):
        """Test listing when no sound cards are available"""
        result, status = get_response(self.handler.handle_list_soundcards())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertIn('data', result)
        self.assertEqual(result['data']['count'], 0)
        self.assertEqual(len(result['data']['soundcards']), 0)


class TestSoundcardHandlerSetDtoverlay(unittest.TestCase):
    """Tests for set_dtoverlay endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'}
    })
    def test_set_dtoverlay_success(self, mock_config_class, mock_request):
        """Test successfully setting dtoverlay"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'dtoverlay': 'hifiberry-amp'}

        mock_config = MagicMock()
        mock_config.changes_made = True
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertIn('dtoverlay', result['data'])

    @patch('src.handlers.soundcard_handler.request')
    def test_set_dtoverlay_no_request_body(self, mock_request):
        """Test set_dtoverlay with no JSON request body"""
        mock_request.is_json = False

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {})
    def test_set_dtoverlay_invalid_overlay(self, mock_request):
        """Test set_dtoverlay with invalid overlay"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'dtoverlay': 'invalid-overlay'}

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-dac': {'dtoverlay': 'hifiberry-dac'}
    })
    def test_set_dtoverlay_no_changes(self, mock_config_class, mock_request):
        """Test set_dtoverlay when config was already set"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'dtoverlay': 'hifiberry-dac'}

        mock_config = MagicMock()
        mock_config.changes_made = False
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['changes_made'])


class TestSoundcardHandlerDetectionStatus(unittest.TestCase):
    """Tests for detection_status endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_detection_status_enabled(self, mock_config_class):
        """Test getting detection status when enabled"""
        mock_config = MagicMock()
        mock_config.is_detection_disabled.return_value = False
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_detection_status())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['data']['detection_enabled'])

    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_detection_status_disabled(self, mock_config_class):
        """Test getting detection status when disabled"""
        mock_config = MagicMock()
        mock_config.is_detection_disabled.return_value = True
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_detection_status())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['detection_enabled'])


class TestSoundcardHandlerEnableDetection(unittest.TestCase):
    """Tests for enable_detection endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_enable_detection_success(self, mock_config_class):
        """Test successfully enabling detection"""
        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_enable_detection())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['data']['detection_enabled'])

    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_enable_detection_already_enabled(self, mock_config_class):
        """Test enabling detection when already enabled"""
        mock_config = MagicMock()
        mock_config.is_detection_disabled.return_value = False
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_enable_detection())
        self.assertEqual(status, 200)
        self.assertIn('detection_enabled', result['data'])


class TestSoundcardHandlerDisableDetection(unittest.TestCase):
    """Tests for disable_detection endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_disable_detection_with_card_name(self, mock_config_class, mock_request):
        """Test disabling detection and setting a specific card"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'card_name': 'hifiberry-amp'}

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        with patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
            'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'}
        }):
            result, status = get_response(self.handler.handle_disable_detection())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['detection_enabled'])

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_disable_detection_without_card_name(self, mock_config_class, mock_request):
        """Test disabling detection without specifying a card"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        result, status = get_response(self.handler.handle_disable_detection())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['detection_enabled'])

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_disable_detection_invalid_card(self, mock_config_class, mock_request):
        """Test disabling detection with invalid card name"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'card_name': 'invalid-card'}

        with patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {}):
            result, status = get_response(self.handler.handle_disable_detection())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_disable_detection_no_request_body(self, mock_config_class, mock_request):
        """Test disabling detection with no request body"""
        mock_request.is_json = False

        result, status = get_response(self.handler.handle_disable_detection())
        self.assertEqual(status, 200)
        # Should still succeed with default behavior


class TestSoundcardHandlerDetectLive(unittest.TestCase):
    """Tests for detect_live_soundcard endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.SoundcardDetector')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'}
    })
    def test_detect_live_card_found(self, mock_detector_class):
        """Test live detection when card is found"""
        mock_detector = MagicMock()
        mock_detector.detected_card = 'hifiberry-amp'
        mock_detector.detected_overlay = 'hifiberry-amp'
        mock_detector_class.return_value = mock_detector

        result, status = get_response(self.handler.handle_detect_live_soundcard())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['data']['card_detected'])
        self.assertEqual(result['data']['card_name'], 'hifiberry-amp')

    @patch('src.handlers.soundcard_handler.SoundcardDetector')
    def test_detect_live_card_not_found(self, mock_detector_class):
        """Test live detection when no card is found"""
        mock_detector = MagicMock()
        mock_detector.detected_card = None
        mock_detector.detected_overlay = None
        mock_detector_class.return_value = mock_detector

        result, status = get_response(self.handler.handle_detect_live_soundcard())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['card_detected'])
        self.assertIsNone(result['data']['card_name'])

    @patch('src.handlers.soundcard_handler.SoundcardDetector')
    def test_detect_live_card_error(self, mock_detector_class):
        """Test live detection with error"""
        mock_detector_class.side_effect = OSError("Hardware error")

        result, status = get_response(self.handler.handle_detect_live_soundcard())
        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')


class TestSoundcardHandlerDetectCurrent(unittest.TestCase):
    """Tests for detect_soundcard endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.Soundcard')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-dac': {'dtoverlay': 'hifiberry-dac'}
    })
    def test_detect_current_card_found(self, mock_soundcard_class):
        """Test detecting currently configured card"""
        mock_card = MagicMock()
        mock_card.name = 'hifiberry-dac'
        mock_card.volume_control = 'PCM'
        mock_card.headphone_volume_control = None
        mock_card.get_hardware_index.return_value = 0
        mock_card.output_channels = 2
        mock_card.input_channels = 0
        mock_card.features = []
        mock_card.hat_name = 'DAC'
        mock_card.supports_dsp = False
        mock_card.card_type = ['DAC']
        mock_soundcard_class.return_value = mock_card

        result, status = get_response(self.handler.handle_detect_soundcard())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['data']['card_detected'])
        self.assertEqual(result['data']['card_name'], 'hifiberry-dac')

    @patch('src.handlers.soundcard_handler.Soundcard')
    def test_detect_current_card_not_found(self, mock_soundcard_class):
        """Test detecting when no card is currently configured"""
        mock_card = MagicMock()
        mock_card.name = None
        mock_soundcard_class.return_value = mock_card

        result, status = get_response(self.handler.handle_detect_soundcard())
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['card_detected'])
        self.assertIsNone(result['data']['card_name'])

    @patch('src.handlers.soundcard_handler.Soundcard')
    def test_detect_current_card_error(self, mock_soundcard_class):
        """Test detecting with error"""
        mock_soundcard_class.side_effect = OSError("Hardware error")

        result, status = get_response(self.handler.handle_detect_soundcard())
        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')


class TestSoundcardHandlerEdgeCases(unittest.TestCase):
    """Tests for edge cases and error conditions"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    @patch('src.handlers.soundcard_handler.request')
    @patch('src.handlers.soundcard_handler.ConfigTxt')
    @patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
        'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'}
    })
    def test_set_dtoverlay_config_file_error(self, mock_config_class, mock_request):
        """Test set_dtoverlay when config file operations fail"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'dtoverlay': 'hifiberry-amp'}

        mock_config_class.side_effect = OSError("Permission denied")

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.request')
    def test_set_dtoverlay_missing_dtoverlay_field(self, mock_request):
        """Test set_dtoverlay when dtoverlay field is missing"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        result, status = get_response(self.handler.handle_set_dtoverlay())
        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.ConfigTxt')
    def test_disable_detection_config_error(self, mock_config_class):
        """Test disable_detection when config operations fail"""
        mock_config_class.side_effect = OSError("File not found")

        result, status = get_response(self.handler.handle_disable_detection())
        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.soundcard_handler.SoundcardDetector')
    def test_detect_live_returns_complete_data(self, mock_detector_class):
        """Test that detect_live returns all required fields"""
        mock_detector = MagicMock()
        mock_detector.detected_card = 'hifiberry-amp'
        mock_detector.detected_overlay = 'hifiberry-amp'
        mock_detector_class.return_value = mock_detector

        with patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {
            'hifiberry-amp': {'dtoverlay': 'hifiberry-amp'}
        }):
            result, status = get_response(self.handler.handle_detect_live_soundcard())

        self.assertIn('card_name', result['data'])
        self.assertIn('overlay', result['data'])
        self.assertIn('dtoverlay', result['data'])
        self.assertIn('card_detected', result['data'])
        self.assertIn('definition_found', result['data'])


class TestSoundcardHandlerResponseFormats(unittest.TestCase):
    """Tests for response format consistency"""

    def setUp(self):
        """Create handler"""
        self.handler = SoundcardHandler()

    def test_all_responses_have_status_field(self):
        """Verify all responses include status field"""
        with patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {}):
            result, _ = get_response(self.handler.handle_list_soundcards())
            self.assertIn('status', result)

    def test_error_responses_have_message(self):
        """Verify error responses include message field"""
        with patch('src.handlers.soundcard_handler.request') as mock_request:
            mock_request.is_json = False
            result, status = get_response(self.handler.handle_set_dtoverlay())
            if status >= 400:
                self.assertIn('message', result)

    def test_success_responses_have_data_field(self):
        """Verify success responses include data field"""
        with patch('src.handlers.soundcard_handler.SOUND_CARD_DEFINITIONS', {}):
            result, status = get_response(self.handler.handle_list_soundcards())
            if status < 400:
                self.assertIn('data', result)


if __name__ == '__main__':
    unittest.main()
