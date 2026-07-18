"""
Comprehensive regression test suite for SystemHandler

Tests all system control API endpoints (reboot, shutdown) with various
delay parameters, validation scenarios, and error handling.
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

from src.handlers.system_handler import SystemHandler  # noqa: E402


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


class TestSystemHandlerReboot(unittest.TestCase):
    """Tests for handle_reboot endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SystemHandler()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_default_delay(self, mock_thread_class, mock_request):
        """Test reboot with default 5 second delay"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)
        self.assertTrue(result['data']['scheduled'])
        mock_thread.start.assert_called_once()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_custom_delay(self, mock_thread_class, mock_request):
        """Test reboot with custom delay parameter"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 30}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 30)
        mock_thread.start.assert_called_once()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_zero_delay(self, mock_thread_class, mock_request):
        """Test reboot with zero second delay (immediate)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 0}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 0)

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_max_delay(self, mock_thread_class, mock_request):
        """Test reboot with maximum 300 second delay"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 300}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 300)

    @patch('src.handlers.system_handler.request')
    def test_reboot_delay_negative(self, mock_request):
        """Test reboot with negative delay (invalid)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': -1}

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 300', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_reboot_delay_too_large(self, mock_request):
        """Test reboot with delay exceeding maximum"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 301}

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 300', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_reboot_delay_invalid_type_string(self, mock_request):
        """Test reboot with delay as string (invalid)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 'invalid'}

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('valid integer', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_reboot_delay_invalid_type_float(self, mock_request):
        """Test reboot with delay as float (invalid)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 10.5}

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 10)

    @patch('src.handlers.system_handler.request')
    def test_reboot_empty_json(self, mock_request):
        """Test reboot with empty JSON body"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        with patch('src.handlers.system_handler.threading.Thread'):
            result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)


class TestSystemHandlerShutdown(unittest.TestCase):
    """Tests for handle_shutdown endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SystemHandler()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_default_delay(self, mock_thread_class, mock_request):
        """Test shutdown with default 5 second delay"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)
        self.assertTrue(result['data']['scheduled'])
        mock_thread.start.assert_called_once()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_custom_delay(self, mock_thread_class, mock_request):
        """Test shutdown with custom delay parameter"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 60}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 60)
        mock_thread.start.assert_called_once()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_zero_delay(self, mock_thread_class, mock_request):
        """Test shutdown with zero second delay (immediate)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 0}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 0)

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_max_delay(self, mock_thread_class, mock_request):
        """Test shutdown with maximum 300 second delay"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 300}
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 300)

    @patch('src.handlers.system_handler.request')
    def test_shutdown_delay_negative(self, mock_request):
        """Test shutdown with negative delay (invalid)"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': -5}

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 300', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_shutdown_delay_too_large(self, mock_request):
        """Test shutdown with delay exceeding maximum"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 600}

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('between 0 and 300', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_shutdown_delay_invalid_type(self, mock_request):
        """Test shutdown with delay as invalid type"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 'not_a_number'}

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('valid integer', result['message'])

    @patch('src.handlers.system_handler.request')
    def test_shutdown_empty_json(self, mock_request):
        """Test shutdown with empty JSON body"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        with patch('src.handlers.system_handler.threading.Thread'):
            result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)


class TestSystemHandlerThreading(unittest.TestCase):
    """Tests for background thread creation and configuration"""

    def setUp(self):
        """Create handler"""
        self.handler = SystemHandler()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_thread_is_daemon(self, mock_thread_class, mock_request):
        """Test that reboot thread is created as daemon"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        self.handler.handle_reboot()

        # Verify Thread was called with daemon=True
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args[1]
        self.assertTrue(call_kwargs.get('daemon'))

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_thread_is_daemon(self, mock_thread_class, mock_request):
        """Test that shutdown thread is created as daemon"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        self.handler.handle_shutdown()

        # Verify Thread was called with daemon=True
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args[1]
        self.assertTrue(call_kwargs.get('daemon'))

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_thread_started(self, mock_thread_class, mock_request):
        """Test that reboot thread is started"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        self.handler.handle_reboot()

        mock_thread.start.assert_called_once()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_thread_started(self, mock_thread_class, mock_request):
        """Test that shutdown thread is started"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        self.handler.handle_shutdown()

        mock_thread.start.assert_called_once()


class TestSystemHandlerResponseFormat(unittest.TestCase):
    """Tests for response format consistency"""

    def setUp(self):
        """Create handler"""
        self.handler = SystemHandler()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_success_response_format(self, mock_thread_class, mock_request):
        """Verify reboot success response has required fields"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('data', result)
        self.assertIn('delay', result['data'])
        self.assertIn('scheduled', result['data'])

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_success_response_format(self, mock_thread_class, mock_request):
        """Verify shutdown success response has required fields"""
        mock_request.is_json = False
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('data', result)
        self.assertIn('delay', result['data'])
        self.assertIn('scheduled', result['data'])

    @patch('src.handlers.system_handler.request')
    def test_reboot_error_response_format(self, mock_request):
        """Verify reboot error response has required fields"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': -1}

        result, status = get_response(self.handler.handle_reboot())

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.system_handler.request')
    def test_shutdown_error_response_format(self, mock_request):
        """Verify shutdown error response has required fields"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {'delay': 500}

        result, status = get_response(self.handler.handle_shutdown())

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertEqual(result['status'], 'error')


class TestSystemHandlerEdgeCases(unittest.TestCase):
    """Tests for edge cases and error conditions"""

    def setUp(self):
        """Create handler"""
        self.handler = SystemHandler()

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_null_json_data(self, mock_thread_class, mock_request):
        """Test reboot when get_json returns None"""
        mock_request.is_json = True
        mock_request.get_json.return_value = None
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_null_json_data(self, mock_thread_class, mock_request):
        """Test shutdown when get_json returns None"""
        mock_request.is_json = True
        mock_request.get_json.return_value = None
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 5)

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_reboot_with_extra_parameters(self, mock_thread_class, mock_request):
        """Test reboot ignores extra parameters in JSON"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'delay': 10,
            'force': True,
            'other_param': 'ignored'
        }
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_reboot())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 10)

    @patch('src.handlers.system_handler.request')
    @patch('src.handlers.system_handler.threading.Thread')
    def test_shutdown_with_extra_parameters(self, mock_thread_class, mock_request):
        """Test shutdown ignores extra parameters in JSON"""
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'delay': 20,
            'force': True,
            'reason': 'maintenance'
        }
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result, status = get_response(self.handler.handle_shutdown())

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['delay'], 20)


if __name__ == '__main__':
    unittest.main()
