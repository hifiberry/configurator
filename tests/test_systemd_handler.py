"""
Comprehensive regression test suite for SystemdHandler

Tests all systemd service operation API endpoints including status, service existence
checks, service listings, and operation execution with permission-based access control.
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

from src.handlers.systemd_handler import SystemdHandler  # noqa: E402


def get_response(result):
    """Helper to extract response and status code from handler result"""
    if isinstance(result, tuple):
        response, status = result[0], result[1]
    else:
        response, status = result, 200

    # Some test modules replace Flask with mocks that return Response-like objects.
    # Normalize those objects to their JSON payload so assertions can treat the
    # response consistently as a dictionary.
    if hasattr(response, 'get_json'):
        json_payload = response.get_json()
        if json_payload is not None:
            response = json_payload

    return response, status


class TestSystemdHandlerOperation(unittest.TestCase):
    """Tests for handle_systemd_operation endpoint"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_start_success(self, mock_config):
        """Test successful start operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.start.return_value = (True, 'Service started')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'start')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['operation'], 'start')
        self.assertEqual(result['data']['service'], 'test-service')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_stop_success(self, mock_config):
        """Test successful stop operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.stop.return_value = (True, 'Service stopped')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'stop')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['operation'], 'stop')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_restart_success(self, mock_config):
        """Test successful restart operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.restart.return_value = (True, 'Service restarted')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'restart')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['operation'], 'restart')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_enable_success(self, mock_config):
        """Test successful enable operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.enable.return_value = (True, 'Service enabled')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'enable')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_disable_success(self, mock_config):
        """Test successful disable operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.disable.return_value = (True, 'Service disabled')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'disable')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_enable_now_success(self, mock_config):
        """Test successful enable-now operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.enable_now.return_value = (True, 'Service enabled and started')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'enable-now')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_disable_now_success(self, mock_config):
        """Test successful disable-now operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.disable_now.return_value = (True, 'Service disabled and stopped')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'disable-now')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_invalid(self, mock_config):
        """Test invalid operation"""
        mock_config.return_value = {'test-service': 'all'}

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'invalid-op')
        )

        self.assertEqual(status, 400)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid operation', result['message'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_service_not_found(self, mock_config):
        """Test operation on non-existent service"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=False)

        result, status = get_response(
            self.handler.handle_systemd_operation('nonexistent', 'start')
        )

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('does not exist', result['message'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_permission_denied(self, mock_config):
        """Test operation not allowed for service permission level"""
        mock_config.return_value = {'test-service': 'status'}
        self.handler._service_exists = MagicMock(return_value=True)

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'start')
        )

        self.assertEqual(status, 403)
        self.assertEqual(result['status'], 'error')
        self.assertIn('not allowed', result['message'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_failure(self, mock_config):
        """Test failed operation"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.start.return_value = (False, 'Permission denied')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'start')
        )

        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to execute', result['message'])


class TestSystemdHandlerStatus(unittest.TestCase):
    """Tests for handle_systemd_status endpoint"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_active_enabled(self, mock_config):
        """Test status of active and enabled service"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'status_output': 'Service is running', 'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['active'], 'active')
        self.assertEqual(result['data']['enabled'], 'enabled')
        self.assertEqual(result['data']['service'], 'test-service')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_inactive_disabled(self, mock_config):
        """Test status of inactive and disabled service"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = False
        self.handler.service_manager.is_enabled.return_value = False
        self.handler.service_manager.status.return_value = (
            True,
            {'status_output': 'Service is not running', 'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['active'], 'inactive')
        self.assertEqual(result['data']['enabled'], 'disabled')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_service_not_found(self, mock_config):
        """Test status of non-existent service"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=False)

        result, status = get_response(
            self.handler.handle_systemd_status('nonexistent')
        )

        self.assertEqual(status, 404)
        self.assertEqual(result['status'], 'error')
        self.assertIn('does not exist', result['message'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_includes_allowed_operations(self, mock_config):
        """Test status includes allowed operations based on permissions"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'status_output': 'Running', 'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertEqual(status, 200)
        self.assertIn('allowed_operations', result['data'])
        self.assertIn('start', result['data']['allowed_operations'])


class TestSystemdHandlerServiceExists(unittest.TestCase):
    """Tests for handle_service_exists endpoint"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_service_exists_yes(self, mock_config):
        """Test check for existing service"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_service_exists('test-service')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['data']['exists'])
        self.assertEqual(result['data']['service'], 'test-service')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_service_exists_no(self, mock_config):
        """Test check for non-existent service"""
        mock_config.return_value = {}
        self.handler._service_exists = MagicMock(return_value=False)

        result, status = get_response(
            self.handler.handle_service_exists('nonexistent')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['data']['exists'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_service_exists_includes_basic_info(self, mock_config):
        """Test service exists response includes basic info when service is found"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = False
        self.handler.service_manager.status.return_value = (
            True,
            {'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_service_exists('test-service')
        )

        self.assertEqual(status, 200)
        self.assertTrue(result['data']['exists'])
        self.assertEqual(result['data']['active'], 'active')
        self.assertEqual(result['data']['enabled'], 'disabled')
        self.assertIn('allowed_operations', result['data'])


class TestSystemdHandlerListServices(unittest.TestCase):
    """Tests for handle_list_services endpoint"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_list_services_empty(self, mock_config):
        """Test list with no configured services"""
        mock_config.return_value = {}

        result, status = get_response(
            self.handler.handle_list_services()
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['count'], 0)
        self.assertEqual(len(result['data']['services']), 0)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_list_services_multiple(self, mock_config):
        """Test list with multiple services"""
        mock_config.return_value = {
            'service1': 'all',
            'service2': 'status'
        }
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_list_services()
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['count'], 2)
        self.assertEqual(len(result['data']['services']), 2)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_list_services_nonexistent(self, mock_config):
        """Test list with non-existent service included"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=False)

        result, status = get_response(
            self.handler.handle_list_services()
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['count'], 1)
        self.assertFalse(result['data']['services'][0]['exists'])
        self.assertEqual(result['data']['services'][0]['active'], 'not-available')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_list_services_permission_levels(self, mock_config):
        """Test list includes correct permission levels and operations"""
        mock_config.return_value = {
            'full-access': 'all',
            'status-only': 'status'
        }
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_list_services()
        )

        self.assertEqual(status, 200)
        services = {s['service']: s for s in result['data']['services']}

        self.assertEqual(services['full-access']['permission_level'], 'all')
        self.assertIn('start', services['full-access']['allowed_operations'])

        self.assertEqual(services['status-only']['permission_level'], 'status')
        self.assertEqual(services['status-only']['allowed_operations'], ['status'])


class TestSystemdHandlerPermissions(unittest.TestCase):
    """Tests for permission-based access control"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_permission_all_allows_all_operations(self, mock_config):
        """Test 'all' permission level allows all operations"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)

        perms = self.handler._get_service_permissions('test-service')

        self.assertIn('start', perms)
        self.assertIn('stop', perms)
        self.assertIn('restart', perms)
        self.assertIn('enable', perms)
        self.assertIn('disable', perms)
        self.assertIn('status', perms)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_permission_status_restricts_operations(self, mock_config):
        """Test 'status' permission level only allows status"""
        mock_config.return_value = {'test-service': 'status'}
        self.handler._service_exists = MagicMock(return_value=True)

        perms = self.handler._get_service_permissions('test-service')

        self.assertEqual(perms, ['status'])
        self.assertNotIn('start', perms)
        self.assertNotIn('stop', perms)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_permission_invalid_defaults_to_status(self, mock_config):
        """Test invalid permission level defaults to status"""
        mock_config.return_value = {'test-service': 'invalid'}

        perms = self.handler._get_service_permissions('test-service')

        self.assertEqual(perms, ['status'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_is_operation_allowed_yes(self, mock_config):
        """Test operation allowed check returns true"""
        mock_config.return_value = {'test-service': 'all'}

        allowed = self.handler._is_operation_allowed('test-service', 'start')

        self.assertTrue(allowed)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_is_operation_allowed_no(self, mock_config):
        """Test operation allowed check returns false"""
        mock_config.return_value = {'test-service': 'status'}

        allowed = self.handler._is_operation_allowed('test-service', 'start')

        self.assertFalse(allowed)


class TestSystemdHandlerEdgeCases(unittest.TestCase):
    """Tests for edge cases and error conditions"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_service_exists_manager_unavailable(self, mock_config):
        """Test service exists check when service manager is None"""
        mock_config.return_value = {}
        self.handler.service_manager = None

        exists = self.handler._service_exists('any-service')

        self.assertFalse(exists)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_execute_systemctl_unknown_operation(self, mock_config):
        """Test execute with unknown operation"""
        returncode, stdout, stderr = self.handler._execute_systemctl('unknown', 'test-service')

        self.assertEqual(returncode, 1)
        self.assertIn('Unknown operation', stderr)

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_with_empty_status_data(self, mock_config):
        """Test status when service manager returns empty data"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (True, {})

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['environment'], 'unknown')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_with_string_status_data(self, mock_config):
        """Test status when service manager returns string data"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (True, 'some output string')

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['data']['environment'], 'unknown')


class TestSystemdHandlerResponseFormat(unittest.TestCase):
    """Tests for response format consistency"""

    def setUp(self):
        """Create handler with mocked service manager"""
        with patch('src.handlers.systemd_handler.SystemdServiceManager'):
            self.handler = SystemdHandler()
            self.handler.service_manager = MagicMock()

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_success_response_format(self, mock_config):
        """Verify operation success response has required fields"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.start.return_value = (True, 'Started')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'start')
        )

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('data', result)
        self.assertIn('service', result['data'])
        self.assertIn('operation', result['data'])
        self.assertIn('output', result['data'])
        self.assertIn('returncode', result['data'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_operation_error_response_format(self, mock_config):
        """Verify operation error response has required fields"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.start.return_value = (False, 'Failed')

        result, status = get_response(
            self.handler.handle_systemd_operation('test-service', 'start')
        )

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('data', result)
        self.assertEqual(result['status'], 'error')

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_status_response_format(self, mock_config):
        """Verify status response has required fields"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'status_output': 'Running', 'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_systemd_status('test-service')
        )

        self.assertIn('status', result)
        self.assertIn('data', result)
        self.assertIn('service', result['data'])
        self.assertIn('active', result['data'])
        self.assertIn('enabled', result['data'])
        self.assertIn('allowed_operations', result['data'])

    @patch('src.handlers.systemd_handler.get_config_section')
    def test_list_services_response_format(self, mock_config):
        """Verify list services response has required fields"""
        mock_config.return_value = {'test-service': 'all'}
        self.handler._service_exists = MagicMock(return_value=True)
        self.handler.service_manager.is_active.return_value = True
        self.handler.service_manager.is_enabled.return_value = True
        self.handler.service_manager.status.return_value = (
            True,
            {'environment': 'system'}
        )

        result, status = get_response(
            self.handler.handle_list_services()
        )

        self.assertIn('status', result)
        self.assertIn('data', result)
        self.assertIn('services', result['data'])
        self.assertIn('count', result['data'])


if __name__ == '__main__':
    unittest.main()
