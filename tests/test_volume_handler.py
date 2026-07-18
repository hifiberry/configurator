"""
Comprehensive regression test suite for VolumeHandler

Tests all volume control API endpoints including headphone volume listing,
getting, setting, storing, and restoring operations.
"""

import unittest
from unittest.mock import patch, MagicMock
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

from src.handlers.volume_handler import VolumeHandler  # noqa: E402


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


class TestVolumeHandlerListControls(unittest.TestCase):
    """Tests for handle_list_headphone_controls endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_success(self, mock_get_controls):
        """Test successful listing of headphone controls"""
        mock_get_controls.return_value = ['Headphone', 'Speaker']

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['data']['controls']), 2)
        self.assertEqual(result['data']['count'], 2)

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_empty(self, mock_get_controls):
        """Test listing when no controls are available"""
        mock_get_controls.return_value = []

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['count'], 0)

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_single(self, mock_get_controls):
        """Test listing with single control"""
        mock_get_controls.return_value = ['Headphone']

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['count'], 1)

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_error(self, mock_get_controls):
        """Test list when error occurs"""
        mock_get_controls.side_effect = Exception('Audio device not found')

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to list', result['message'])


class TestVolumeHandlerGetVolume(unittest.TestCase):
    """Tests for handle_get_headphone_volume endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_success(self, mock_get_volume):
        """Test successful retrieval of headphone volume"""
        mock_get_volume.return_value = (75, 'Headphone')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['volume'], 75)
        self.assertEqual(result['data']['control'], 'Headphone')

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_zero(self, mock_get_volume):
        """Test getting volume when set to 0"""
        mock_get_volume.return_value = (0, 'Speaker')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 0)

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_max(self, mock_get_volume):
        """Test getting volume when set to maximum"""
        mock_get_volume.return_value = (100, 'Headphone')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 100)

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_not_available(self, mock_get_volume):
        """Test getting volume when no controls available"""
        mock_get_volume.return_value = (None, None)

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('No headphone volume', result['message'])

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_error(self, mock_get_volume):
        """Test get when error occurs"""
        mock_get_volume.side_effect = Exception('ALSA error')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to get', result['message'])


class TestVolumeHandlerSetVolume(unittest.TestCase):
    """Tests for handle_set_headphone_volume endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_success(self, mock_set_volume, mock_request):
        """Test successful setting of headphone volume"""
        mock_request.get_json.return_value = {'volume': 50}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['volume'], 50)
        mock_set_volume.assert_called_once_with('50')

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_zero(self, mock_set_volume, mock_request):
        """Test setting volume to 0 (mute)"""
        mock_request.get_json.return_value = {'volume': 0}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 0)

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_max(self, mock_set_volume, mock_request):
        """Test setting volume to 100 (maximum)"""
        mock_request.get_json.return_value = {'volume': 100}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 100)

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_negative(self, mock_request):
        """Test setting volume to negative value (invalid)"""
        mock_request.get_json.return_value = {'volume': -10}

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 100', result['message'])

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_exceeds_max(self, mock_request):
        """Test setting volume above 100 (invalid)"""
        mock_request.get_json.return_value = {'volume': 150}

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 100', result['message'])

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_invalid_type(self, mock_request):
        """Test setting volume with invalid type (string)"""
        mock_request.get_json.return_value = {'volume': 'invalid'}

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('valid integer', result['message'])

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_float(self, mock_set_volume, mock_request):
        """Test setting volume with float (should convert to int)"""
        mock_request.get_json.return_value = {'volume': 50.7}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 50)

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_missing_parameter(self, mock_request):
        """Test setting volume without volume parameter"""
        mock_request.get_json.return_value = {'other': 'data'}

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('volume parameter is required', result['message'])

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_no_json_data(self, mock_request):
        """Test setting volume with no JSON data"""
        mock_request.get_json.return_value = None

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('No JSON data', result['message'])

    @patch('src.handlers.volume_handler.request')
    def test_set_volume_empty_json(self, mock_request):
        """Test setting volume with empty JSON object"""
        mock_request.get_json.return_value = {}

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 400)
        self.assertIn('No JSON data', result['message'])

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_not_available(self, mock_set_volume, mock_request):
        """Test setting volume when no controls available"""
        mock_request.get_json.return_value = {'volume': 50}
        mock_set_volume.return_value = False

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('No headphone volume', result['message'])

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_error(self, mock_set_volume, mock_request):
        """Test set when error occurs"""
        mock_request.get_json.return_value = {'volume': 50}
        mock_set_volume.side_effect = Exception('ALSA error')

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to set', result['message'])


class TestVolumeHandlerStoreVolume(unittest.TestCase):
    """Tests for handle_store_headphone_volume endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.store_headphone_volume')
    def test_store_volume_success(self, mock_store):
        """Test successful storing of headphone volume"""
        mock_store.return_value = True

        result, status = get_response(self.handler.handle_store_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertIn('stored successfully', result['message'])

    @patch('src.handlers.volume_handler.store_headphone_volume')
    def test_store_volume_not_available(self, mock_store):
        """Test storing when no controls available"""
        mock_store.return_value = False

        result, status = get_response(self.handler.handle_store_headphone_volume())

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('No headphone volume', result['message'])

    @patch('src.handlers.volume_handler.store_headphone_volume')
    def test_store_volume_error(self, mock_store):
        """Test store when error occurs"""
        mock_store.side_effect = Exception('File write error')

        result, status = get_response(self.handler.handle_store_headphone_volume())

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to store', result['message'])


class TestVolumeHandlerRestoreVolume(unittest.TestCase):
    """Tests for handle_restore_headphone_volume endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.restore_headphone_volume')
    def test_restore_volume_success(self, mock_restore):
        """Test successful restoring of headphone volume"""
        mock_restore.return_value = True

        result, status = get_response(self.handler.handle_restore_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertIn('restored successfully', result['message'])

    @patch('src.handlers.volume_handler.restore_headphone_volume')
    def test_restore_volume_not_available(self, mock_restore):
        """Test restoring when no settings or controls available"""
        mock_restore.return_value = False

        result, status = get_response(self.handler.handle_restore_headphone_volume())

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('No headphone volume settings', result['message'])

    @patch('src.handlers.volume_handler.restore_headphone_volume')
    def test_restore_volume_error(self, mock_restore):
        """Test restore when error occurs"""
        mock_restore.side_effect = Exception('File read error')

        result, status = get_response(self.handler.handle_restore_headphone_volume())

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to restore', result['message'])


class TestVolumeHandlerResponseFormat(unittest.TestCase):
    """Tests for response format consistency"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_response_format(self, mock_get_controls):
        """Verify list controls response has required fields"""
        mock_get_controls.return_value = ['Headphone']

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertIn('status', result)
        self.assertIn('data', result)
        self.assertIn('controls', result['data'])
        self.assertIn('count', result['data'])

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_response_format(self, mock_get_volume):
        """Verify get volume response has required fields"""
        mock_get_volume.return_value = (75, 'Headphone')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertIn('status', result)
        self.assertIn('data', result)
        self.assertIn('volume', result['data'])
        self.assertIn('control', result['data'])

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_response_format(self, mock_set_volume, mock_request):
        """Verify set volume response has required fields"""
        mock_request.get_json.return_value = {'volume': 50}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('data', result)
        self.assertIn('volume', result['data'])

    @patch('src.handlers.volume_handler.store_headphone_volume')
    def test_store_volume_response_format(self, mock_store):
        """Verify store volume response has required fields"""
        mock_store.return_value = True

        result, status = get_response(self.handler.handle_store_headphone_volume())

        self.assertIn('status', result)
        self.assertIn('message', result)

    @patch('src.handlers.volume_handler.restore_headphone_volume')
    def test_restore_volume_response_format(self, mock_restore):
        """Verify restore volume response has required fields"""
        mock_restore.return_value = True

        result, status = get_response(self.handler.handle_restore_headphone_volume())

        self.assertIn('status', result)
        self.assertIn('message', result)


class TestVolumeHandlerEdgeCases(unittest.TestCase):
    """Tests for edge cases and error conditions"""

    def setUp(self):
        """Create handler"""
        self.handler = VolumeHandler()

    @patch('src.handlers.volume_handler.get_available_headphone_controls')
    def test_list_controls_many(self, mock_get_controls):
        """Test listing many headphone controls"""
        controls = [f'Control{i}' for i in range(10)]
        mock_get_controls.return_value = controls

        result, status = get_response(self.handler.handle_list_headphone_controls())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['count'], 10)

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_with_extra_params(self, mock_set_volume, mock_request):
        """Test setting volume ignores extra parameters"""
        mock_request.get_json.return_value = {
            'volume': 50,
            'extra': 'ignored',
            'device': 'headphone'
        }
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 50)

    @patch('src.handlers.volume_handler.get_headphone_volume')
    def test_get_volume_fractional_input(self, mock_get_volume):
        """Test getting volume handles fractional values from backend"""
        mock_get_volume.return_value = (75.5, 'Headphone')

        result, status = get_response(self.handler.handle_get_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 75)

    @patch('src.handlers.volume_handler.request')
    @patch('src.handlers.volume_handler.set_headphone_volume')
    def test_set_volume_string_integer(self, mock_set_volume, mock_request):
        """Test setting volume with string that can be converted to int"""
        mock_request.get_json.return_value = {'volume': '60'}
        mock_set_volume.return_value = True

        result, status = get_response(self.handler.handle_set_headphone_volume())

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['volume'], 60)
        mock_set_volume.assert_called_once_with('60')


if __name__ == '__main__':
    unittest.main()
