#!/usr/bin/env python3
"""
Regression tests for BLE provisioning handler.

Tests BLE provisioning service control via systemctl commands including
status checking, starting (with network check override), and stopping.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

# Mock Flask before importing handler
import sys

class MockResponse:
    """Mock Flask Response object"""
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def get_json(self):
        return self.json_data

    def __getitem__(self, key):
        """Support tuple unpacking and dictionary-like access"""
        # Support integer indexing for tuple unpacking
        if isinstance(key, int):
            if key == 0:
                return self
            elif key == 1:
                return self.status_code
            raise IndexError("list index out of range")
        # Support string key access to underlying JSON data
        if isinstance(key, str) and isinstance(self.json_data, dict):
            return self.json_data[key]
        raise KeyError(key)

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

from src.handlers.ble_handler import BLEProvisioningHandler  # noqa: E402


class TestBLEProvisioningHandlerGetStatus(unittest.TestCase):
    """Test BLE provisioning status checking"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BLEProvisioningHandler()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_active(self, mock_run):
        """Test getting status when service is active"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['data']['active'])
        self.assertEqual(data['data']['state'], 'active')
        mock_run.assert_called_once()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_inactive(self, mock_run):
        """Test getting status when service is inactive"""
        mock_result = Mock()
        mock_result.returncode = 3  # Service inactive
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['data']['active'])
        self.assertEqual(data['data']['state'], 'unknown')

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_command_timeout(self, mock_run):
        """Test status check with timeout exception"""
        mock_run.side_effect = TimeoutError("Command timed out")

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Command timed out', data['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_command_error(self, mock_run):
        """Test status check with generic exception"""
        mock_run.side_effect = Exception("systemctl not found")

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('systemctl not found', data['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_call_parameters(self, mock_run):
        """Test that get_status calls systemctl with correct parameters"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        self.handler.handle_get_status()

        mock_run.assert_called_once_with(
            ["systemctl", "is-active", "ble-provisioning"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )


class TestBLEProvisioningHandlerStart(unittest.TestCase):
    """Test BLE provisioning service start"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BLEProvisioningHandler()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_success(self, mock_run):
        """Test successful start of BLE provisioning"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        response = self.handler.handle_start()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIn('started', data['message'].lower())

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_failure(self, mock_run):
        """Test failed start of BLE provisioning"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Unit not found\n"
        mock_run.return_value = mock_result

        response = self.handler.handle_start()
        data, status_code = response

        self.assertEqual(status_code, 500)
        self.assertEqual(data.get_json()['status'], 'error')
        self.assertIn('Failed to start', data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_exception(self, mock_run):
        """Test start with exception"""
        mock_run.side_effect = Exception("Permission denied")

        response = self.handler.handle_start()
        data, status_code = response

        self.assertEqual(status_code, 500)
        self.assertEqual(data.get_json()['status'], 'error')
        self.assertIn('Permission denied', data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_creates_override(self, mock_run):
        """Test that start creates systemd override directory"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_start()

        # Verify mkdir was called
        mkdir_call = mock_run.call_args_list[0]
        self.assertEqual(mkdir_call[0][0][0], "mkdir")
        self.assertIn("-p", mkdir_call[0][0])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_creates_override_config(self, mock_run):
        """Test that start creates override configuration"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_start()

        # Verify bash -c echo was called
        echo_call = mock_run.call_args_list[1]
        self.assertEqual(echo_call[0][0][0], "bash")
        self.assertEqual(echo_call[0][0][1], "-c")
        self.assertIn("ExecStartPre=", echo_call[0][0][2])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_daemon_reload(self, mock_run):
        """Test that start calls daemon-reload"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_start()

        # Verify daemon-reload was called
        daemon_reload_call = mock_run.call_args_list[2]
        self.assertEqual(daemon_reload_call[0][0][0], "systemctl")
        self.assertEqual(daemon_reload_call[0][0][1], "daemon-reload")

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_calls_systemctl_start(self, mock_run):
        """Test that start calls systemctl start"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_start()

        # Verify systemctl start was called
        start_call = mock_run.call_args_list[3]
        self.assertEqual(start_call[0][0][0], "systemctl")
        self.assertEqual(start_call[0][0][1], "start")
        self.assertEqual(start_call[0][0][2], "ble-provisioning")

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_check_parameter(self, mock_run):
        """Test that all subprocess calls use check=False"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_start()

        # All calls should have check=False
        for call_args in mock_run.call_args_list:
            self.assertFalse(call_args[1].get('check', False))


class TestBLEProvisioningHandlerStop(unittest.TestCase):
    """Test BLE provisioning service stop"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BLEProvisioningHandler()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_success(self, mock_run):
        """Test successful stop of BLE provisioning"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        response = self.handler.handle_stop()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIn('stopped', data['message'].lower())

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_failure(self, mock_run):
        """Test failed stop of BLE provisioning"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Unit not loaded\n"
        mock_run.return_value = mock_result

        response = self.handler.handle_stop()
        data, status_code = response

        self.assertEqual(status_code, 500)
        self.assertEqual(data.get_json()['status'], 'error')
        self.assertIn('Failed to stop', data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_exception(self, mock_run):
        """Test stop with exception"""
        mock_run.side_effect = Exception("Connection refused")

        response = self.handler.handle_stop()
        data, status_code = response

        self.assertEqual(status_code, 500)
        self.assertEqual(data.get_json()['status'], 'error')
        self.assertIn('Connection refused', data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_calls_systemctl_stop(self, mock_run):
        """Test that stop calls systemctl stop"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_stop()

        # Verify systemctl stop was called first
        stop_call = mock_run.call_args_list[0]
        self.assertEqual(stop_call[0][0][0], "systemctl")
        self.assertEqual(stop_call[0][0][1], "stop")
        self.assertEqual(stop_call[0][0][2], "ble-provisioning")

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_removes_override_directory(self, mock_run):
        """Test that stop removes systemd override directory"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_stop()

        # Verify rm -rf was called
        rm_call = mock_run.call_args_list[1]
        self.assertEqual(rm_call[0][0][0], "rm")
        self.assertEqual(rm_call[0][0][1], "-rf")
        self.assertIn("ble-provisioning", rm_call[0][0][2])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_daemon_reload(self, mock_run):
        """Test that stop calls daemon-reload"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_stop()

        # Verify daemon-reload was called
        daemon_reload_call = mock_run.call_args_list[2]
        self.assertEqual(daemon_reload_call[0][0][0], "systemctl")
        self.assertEqual(daemon_reload_call[0][0][1], "daemon-reload")

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_check_parameter(self, mock_run):
        """Test that all subprocess calls use check=False"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        self.handler.handle_stop()

        # All calls should have check=False
        for call_args in mock_run.call_args_list:
            self.assertFalse(call_args[1].get('check', False))


class TestBLEProvisioningHandlerReturnTypes(unittest.TestCase):
    """Test return type annotations"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BLEProvisioningHandler()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_returns_response(self, mock_run):
        """Test that get_status returns Response"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        result = self.handler.handle_get_status()
        # Response should have get_json method
        self.assertTrue(hasattr(result, 'get_json'))
        self.assertTrue(callable(result.get_json))

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_returns_response_or_tuple(self, mock_run):
        """Test that start returns Response or tuple"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = self.handler.handle_start()
        # Should have get_json (Response object)
        self.assertTrue(hasattr(result, 'get_json'))

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_error_returns_tuple(self, mock_run):
        """Test that start error returns tuple with status code"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error\n"
        mock_run.return_value = mock_result

        result = self.handler.handle_start()
        # Should be tuple (response, status_code)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1], 500)

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_returns_response_or_tuple(self, mock_run):
        """Test that stop returns Response or tuple"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = self.handler.handle_stop()
        # Should have get_json (Response object)
        self.assertTrue(hasattr(result, 'get_json'))

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_error_returns_tuple(self, mock_run):
        """Test that stop error returns tuple with status code"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error\n"
        mock_run.return_value = mock_result

        result = self.handler.handle_stop()
        # Should be tuple (response, status_code)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1], 500)


class TestBLEProvisioningHandlerEdgeCases(unittest.TestCase):
    """Test edge cases and robustness"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = BLEProvisioningHandler()

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_with_empty_stdout(self, mock_run):
        """Test get_status when stdout is empty"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(data['data']['state'], 'unknown')

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_start_with_stderr_in_error_response(self, mock_run):
        """Test that start includes stderr in error message"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Critical error message"
        mock_run.return_value = mock_result

        response = self.handler.handle_start()
        data, _ = response

        self.assertIn("Critical error message", data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_stop_with_stderr_in_error_response(self, mock_run):
        """Test that stop includes stderr in error message"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Another error"
        mock_run.return_value = mock_result

        response = self.handler.handle_stop()
        data, _ = response

        self.assertIn("Another error", data.get_json()['message'])

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_get_status_with_extra_whitespace(self, mock_run):
        """Test get_status strips whitespace from stdout"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "  active  \n"
        mock_run.return_value = mock_result

        response = self.handler.handle_get_status()
        data = response.get_json()

        self.assertEqual(data['data']['state'], 'active')

    @patch('src.handlers.ble_handler.subprocess.run')
    def test_multiple_sequential_operations(self, mock_run):
        """Test multiple sequential operations"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "active\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Check status
        response1 = self.handler.handle_get_status()
        self.assertEqual(response1.get_json()['status'], 'success')

        # Stop service
        response2 = self.handler.handle_stop()
        self.assertEqual(response2.get_json()['status'], 'success')

        # Start service
        response3 = self.handler.handle_start()
        self.assertEqual(response3.get_json()['status'], 'success')

        # Check status again
        response4 = self.handler.handle_get_status()
        self.assertEqual(response4.get_json()['status'], 'success')


if __name__ == '__main__':
    unittest.main()
