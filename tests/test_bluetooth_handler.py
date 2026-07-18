#!/usr/bin/env python3
"""
Regression tests for Bluetooth handler.

Tests Bluetooth configuration API endpoints including passkey management,
modal handling, and device management operations.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock dbus_fast and other dependencies before importing bluetooth module
sys.modules['dbus_fast'] = MagicMock()
sys.modules['dbus_fast.aio'] = MagicMock()
sys.modules['dbus_fast.service'] = MagicMock()
sys.modules['dbus_fast.constants'] = MagicMock()

# Mock Flask before importing handler
class MockResponse:
    """Mock Flask Response object"""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def get_json(self):
        """Return the mocked JSON payload."""
        return self.json_data

    def __getitem__(self, key):
        """Support tuple unpacking"""
        if key == 0:
            return self
        if key == 1:
            return self.status_code
        raise IndexError("list index out of range")

    def __len__(self):
        """Support len() for tuple detection"""
        return 2

    def __iter__(self):
        """Support iteration for tuple unpacking"""
        return iter([self, self.status_code])


def mock_jsonify(data):
    """Mock Flask jsonify function"""
    return MockResponse(data, 200)


flask_mock = MagicMock()
flask_mock.jsonify = mock_jsonify
flask_mock.Response = MockResponse
sys.modules['flask'] = flask_mock

from src.handlers.bluetooth_handler import BluetoothHandler  # pylint: disable=wrong-import-position  # noqa: E402


class TestBluetoothHandlerPasskey(unittest.TestCase):
    """Test Bluetooth passkey management"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    def test_set_passkey_from_args(self):
        """Test setting passkey from query arguments"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = "123456"
            mock_request.is_json = False

            response = self.handler.handle_set_bluetooth_passkey()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(self.handler.passkey, "123456")

    def test_set_passkey_from_json(self):
        """Test setting passkey from JSON body"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = None
            mock_request.is_json = True
            mock_request.json.get.return_value = "654321"

            response = self.handler.handle_set_bluetooth_passkey()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(self.handler.passkey, "654321")

    def test_set_passkey_missing(self):
        """Test setting passkey with missing value"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = None
            mock_request.is_json = False

            response, status_code = self.handler.handle_set_bluetooth_passkey()
            data = response.get_json()

            self.assertEqual(status_code, 400)
            self.assertEqual(data['status'], 'error')
            self.assertIn('No passkey provided', data['message'])

    def test_get_passkey(self):
        """Test getting stored passkey"""
        self.handler.passkey = "test-passkey"

        response = self.handler.handle_get_bluetooth_passkey()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['passkey'], 'test-passkey')
        # Passkey should be cleared after retrieval
        self.assertIsNone(self.handler.passkey)

    def test_get_passkey_empty(self):
        """Test getting passkey when none is stored"""
        response = self.handler.handle_get_bluetooth_passkey()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIsNone(data['passkey'])

    def test_set_passkey_exception(self):
        """Test passkey setting with exception"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.side_effect = RuntimeError("Request error")

            response, status_code = self.handler.handle_set_bluetooth_passkey()
            data = response.get_json()

            self.assertEqual(status_code, 500)
            self.assertEqual(data['status'], 'error')


class TestBluetoothHandlerModal(unittest.TestCase):
    """Test Bluetooth modal management"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    def test_set_modal_from_args(self):
        """Test setting modal from query arguments"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = "pair-device"
            mock_request.is_json = False

            response = self.handler.handle_set_show_modal()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(self.handler.show_modal, "pair-device")

    def test_set_modal_from_json(self):
        """Test setting modal from JSON body"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = None
            mock_request.is_json = True
            mock_request.json.get.return_value = "connect-device"

            response = self.handler.handle_set_show_modal()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(self.handler.show_modal, "connect-device")

    def test_set_modal_missing(self):
        """Test setting modal with missing value"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = None
            mock_request.is_json = False

            response, status_code = self.handler.handle_set_show_modal()
            data = response.get_json()

            self.assertEqual(status_code, 400)
            self.assertEqual(data['status'], 'error')
            self.assertIn('No modal value provided', data['message'])

    def test_get_modal(self):
        """Test getting stored modal"""
        self.handler.show_modal = "test-modal"

        response = self.handler.handle_get_show_modal()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['modal'], 'test-modal')
        # Modal should be cleared after retrieval
        self.assertIsNone(self.handler.show_modal)

    def test_get_modal_empty(self):
        """Test getting modal when none is stored"""
        response = self.handler.handle_get_show_modal()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIsNone(data['modal'])

    def test_set_modal_exception(self):
        """Test modal setting with exception"""
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.side_effect = RuntimeError("Request error")

            response, status_code = self.handler.handle_set_show_modal()
            data = response.get_json()

            self.assertEqual(status_code, 500)
            self.assertEqual(data['status'], 'error')


class TestBluetoothHandlerSettings(unittest.TestCase):
    """Test Bluetooth settings management"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    @patch('src.handlers.bluetooth_handler.get_bluetooth_settings')
    def test_get_settings(self, mock_get_settings):
        """Test getting Bluetooth settings"""
        mock_settings = {'power': True, 'discoverability': True}
        mock_get_settings.return_value = mock_settings

        response = self.handler.handle_get_bluetooth_settings()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data'], mock_settings)

    @patch('src.handlers.bluetooth_handler.get_bluetooth_settings')
    def test_get_settings_error(self, mock_get_settings):
        """Test getting settings with error"""
        mock_get_settings.side_effect = RuntimeError("Bluetooth service error")

        response, status_code = self.handler.handle_get_bluetooth_settings()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Failed to retrieve', data['message'])

    @patch('src.handlers.bluetooth_handler.set_bluetooth_settings')
    @patch('src.handlers.bluetooth_handler.request')
    def test_set_settings(self, mock_request, mock_set_settings):
        """Test setting Bluetooth settings"""
        mock_request.args = {'power': 'true'}
        mock_settings = {'power': True}
        mock_set_settings.return_value = mock_settings

        response = self.handler.handle_set_bluetooth_settings()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data'], mock_settings)

    @patch('src.handlers.bluetooth_handler.set_bluetooth_settings')
    @patch('src.handlers.bluetooth_handler.request')
    def test_set_settings_error(self, mock_request, mock_set_settings):
        """Test setting settings with error"""
        mock_request.args = {}
        mock_set_settings.side_effect = RuntimeError("Invalid setting")

        response, status_code = self.handler.handle_set_bluetooth_settings()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Failed to set', data['message'])


class TestBluetoothHandlerDevices(unittest.TestCase):
    """Test Bluetooth device management"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    @patch('src.handlers.bluetooth_handler.get_paired_devices', new_callable=Mock)
    def test_get_paired_devices(self, mock_get_devices):
        """Test getting paired devices"""
        # Mock returns a list-like object
        mock_devices = [
            {'address': '00:11:22:33:44:55', 'name': 'Device1'},
            {'address': '00:11:22:33:44:66', 'name': 'Device2'},
        ]
        mock_get_devices.return_value = mock_devices

        response = self.handler.handle_get_paired_devices()
        # Handle both Response and tuple returns
        if isinstance(response, tuple):
            response, _ = response
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIsNotNone(data.get('data'))

    @patch('src.handlers.bluetooth_handler.get_paired_devices', new_callable=Mock)
    def test_get_paired_devices_empty(self, mock_get_devices):
        """Test getting paired devices when list is empty"""
        mock_get_devices.return_value = []

        response = self.handler.handle_get_paired_devices()
        # Handle both Response and tuple returns
        if isinstance(response, tuple):
            response, _ = response
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')

    @patch('src.handlers.bluetooth_handler.unpair_device', new_callable=Mock)
    @patch('src.handlers.bluetooth_handler.request')
    def test_unpair_device_success(self, mock_request, mock_unpair):
        """Test unpairing device successfully"""
        mock_request.args.get.return_value = "00:11:22:33:44:55"
        mock_unpair.return_value = {'status': 'unpaired'}

        response = self.handler.handle_unpair_device()
        # Handle both Response and tuple returns
        if isinstance(response, tuple):
            response, status_code = response
        else:
            status_code = response.status_code
        data = response.get_json()

        self.assertEqual(status_code, 200)
        self.assertEqual(data['status'], 'success')
        mock_unpair.assert_called_once_with("00:11:22:33:44:55")


class TestBluetoothHandlerDeviceRegression(unittest.TestCase):
    """Regression tests for device branch error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.handler = BluetoothHandler()

    def test_get_paired_devices_returns_data_payload(self):
        """Regression: success payload should include paired device data."""
        devices = [{'address': '00:11:22:33:44:55', 'name': 'Device 1'}]
        with patch(
            'src.handlers.bluetooth_handler.get_paired_devices',
            new=Mock(return_value=devices),
        ):
            response = self.handler.handle_get_paired_devices()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data'], devices)

    def test_get_paired_devices_returns_500_on_exception(self):
        """Regression: runtime failures return 500 with an error payload."""
        with patch(
            'src.handlers.bluetooth_handler.get_paired_devices',
            new=Mock(side_effect=RuntimeError('Bluetooth error')),
        ):
            response, status_code = self.handler.handle_get_paired_devices()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Failed to retrieve paired devices', data['message'])
        self.assertEqual(data['error'], 'Bluetooth error')

    @patch('src.handlers.bluetooth_handler.request')
    def test_unpair_device_returns_400_on_value_error(self, mock_request):
        """Regression: validation errors should map to HTTP 400."""
        mock_request.args.get.return_value = '00:11:22:33:44:FF'

        with patch(
            'src.handlers.bluetooth_handler.unpair_device',
            new=Mock(side_effect=ValueError('Device not found')),
        ):
            response, status_code = self.handler.handle_unpair_device()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Device not found')

    @patch('src.handlers.bluetooth_handler.request')
    def test_unpair_device_returns_500_on_runtime_error(self, mock_request):
        """Regression: unexpected unpair errors should map to HTTP 500."""
        mock_request.args.get.return_value = '00:11:22:33:44:55'

        with patch(
            'src.handlers.bluetooth_handler.unpair_device',
            new=Mock(side_effect=RuntimeError('Unpair failed')),
        ):
            response, status_code = self.handler.handle_unpair_device()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Failed to unpair device', data['message'])
        self.assertEqual(data['error'], 'Unpair failed')


class TestBluetoothHandlerReturnTypes(unittest.TestCase):
    """Test return type annotations"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    def test_get_passkey_returns_response(self):
        """Test that get_passkey returns Response"""
        result = self.handler.handle_get_bluetooth_passkey()
        self.assertTrue(hasattr(result, 'get_json'))
        self.assertTrue(callable(result.get_json))

    @patch('src.handlers.bluetooth_handler.request')
    def test_set_passkey_returns_response_or_tuple(self, mock_request):
        """Test that set_passkey returns Response or tuple"""
        mock_request.args.get.return_value = "test"
        mock_request.is_json = False

        result = self.handler.handle_set_bluetooth_passkey()
        self.assertTrue(hasattr(result, 'get_json'))

    @patch('src.handlers.bluetooth_handler.get_bluetooth_settings')
    def test_get_settings_returns_response(self, mock_get_settings):
        """Test that get_settings returns Response"""
        mock_get_settings.return_value = {}

        result = self.handler.handle_get_bluetooth_settings()
        self.assertTrue(hasattr(result, 'get_json'))

    @patch('src.handlers.bluetooth_handler.get_paired_devices', new_callable=Mock)
    def test_get_devices_returns_response(self, mock_get_devices):
        """Test that get_devices returns Response"""
        mock_get_devices.return_value = []

        result = self.handler.handle_get_paired_devices()
        self.assertTrue(hasattr(result, 'get_json'))


class TestBluetoothHandlerEdgeCases(unittest.TestCase):
    """Test edge cases and robustness"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BluetoothHandler()

    def test_passkey_lifecycle(self):
        """Test complete passkey lifecycle"""
        # Set passkey
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = "lifecycle-test"
            mock_request.is_json = False
            response = self.handler.handle_set_bluetooth_passkey()
            self.assertEqual(response.get_json()['status'], 'success')

        # Verify it's stored
        self.assertEqual(self.handler.passkey, "lifecycle-test")

        # Get passkey
        response = self.handler.handle_get_bluetooth_passkey()
        data = response.get_json()
        self.assertEqual(data['passkey'], "lifecycle-test")

        # Verify it's cleared
        self.assertIsNone(self.handler.passkey)

    def test_modal_lifecycle(self):
        """Test complete modal lifecycle"""
        # Set modal
        with patch('src.handlers.bluetooth_handler.request') as mock_request:
            mock_request.args.get.return_value = "lifecycle-modal"
            mock_request.is_json = False
            response = self.handler.handle_set_show_modal()
            self.assertEqual(response.get_json()['status'], 'success')

        # Verify it's stored
        self.assertEqual(self.handler.show_modal, "lifecycle-modal")

        # Get modal
        response = self.handler.handle_get_show_modal()
        data = response.get_json()
        self.assertEqual(data['modal'], "lifecycle-modal")

        # Verify it's cleared
        self.assertIsNone(self.handler.show_modal)

    @patch('src.handlers.bluetooth_handler.request')
    def test_set_passkey_prefers_args_over_json(self, mock_request):
        """Test that query args are preferred over JSON body"""
        mock_request.args.get.return_value = "from-args"
        mock_request.is_json = True
        mock_request.json.get.return_value = "from-json"

        self.handler.handle_set_bluetooth_passkey()
        self.assertEqual(self.handler.passkey, "from-args")

    @patch('src.handlers.bluetooth_handler.request')
    def test_set_modal_prefers_args_over_json(self, mock_request):
        """Test that query args are preferred over JSON body for modal"""
        mock_request.args.get.return_value = "from-args"
        mock_request.is_json = True
        mock_request.json.get.return_value = "from-json"

        self.handler.handle_set_show_modal()
        self.assertEqual(self.handler.show_modal, "from-args")

    def test_handler_instance_isolation(self):
        """Test that handler instances are isolated"""
        handler1 = BluetoothHandler()
        handler2 = BluetoothHandler()

        handler1.passkey = "passkey1"
        handler2.passkey = "passkey2"

        self.assertEqual(handler1.passkey, "passkey1")
        self.assertEqual(handler2.passkey, "passkey2")


if __name__ == '__main__':
    unittest.main()
