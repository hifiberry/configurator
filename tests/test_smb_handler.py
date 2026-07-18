#!/usr/bin/env python3
"""
Regression tests for SMB Handler.

Tests SMB server discovery, connection testing, share listing,
mount configuration management, and error handling.
"""

# pylint: disable=import-error,too-many-public-methods
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

# Mock Flask response class before importing handler
class MockResponse:  # pylint: disable=too-few-public-methods
    """Mock Flask Response object"""

    def __init__(self, json_data=None, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.headers = {}

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


def get_response(result):
    """Extract response object and status code from handler result."""
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, 200


def mock_jsonify(data):
    """Mock Flask jsonify function"""
    return MockResponse(data, 200)


flask_mock = MagicMock()
flask_mock.jsonify = mock_jsonify
flask_mock.Response = MockResponse
sys.modules['flask'] = flask_mock

# pylint: disable=wrong-import-position
from src.handlers.smb_handler import (  # noqa: E402
    SMBHandler,
    load_mount_state,
    save_mount_state,
    get_mount_key,
    unmount_share
)


class TestSMBHandlerStateManagement(unittest.TestCase):
    """Test mount state load/save functionality"""

    def setUp(self):
        """Create handler with temp state file"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, 'state.json')

    def tearDown(self):
        """Clean up temp files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_state_file_not_found(self):
        """Test loading state when file doesn't exist"""
        with patch('src.handlers.smb_handler.os.path.exists', return_value=False):
            result = load_mount_state()
            self.assertEqual(result, {})

    def test_load_state_valid_json(self):
        """Test loading valid state from JSON file"""
        test_state = {'server/share': '/mnt/test'}
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(test_state, f)

        with patch('src.handlers.smb_handler.SAMBA_STATE_FILE', self.state_file):
            result = load_mount_state()
            self.assertEqual(result, test_state)

    def test_load_state_invalid_json(self):
        """Test loading state with invalid JSON"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            f.write('invalid json')

        with patch('src.handlers.smb_handler.SAMBA_STATE_FILE', self.state_file):
            result = load_mount_state()
            self.assertEqual(result, {})

    def test_save_state_valid(self):
        """Test saving valid state to JSON file"""
        test_state = {'server/share': '/mnt/test', 'server2/share2': '/mnt/test2'}
        
        with patch('src.handlers.smb_handler.SAMBA_STATE_FILE', self.state_file):
            save_mount_state(test_state)

        with open(self.state_file, 'r', encoding='utf-8') as f:
            saved_state = json.load(f)
        self.assertEqual(saved_state, test_state)

    def test_save_state_empty(self):
        """Test saving empty state"""
        with patch('src.handlers.smb_handler.SAMBA_STATE_FILE', self.state_file):
            save_mount_state({})

        with open(self.state_file, 'r', encoding='utf-8') as f:
            saved_state = json.load(f)
        self.assertEqual(saved_state, {})


class TestSMBHandlerUtilities(unittest.TestCase):
    """Test utility functions"""

    def test_get_mount_key_basic(self):
        """Test mount key generation"""
        key = get_mount_key('server', 'share')
        self.assertEqual(key, 'server/share')

    def test_get_mount_key_with_special_chars(self):
        """Test mount key with special characters"""
        key = get_mount_key('server-1', 'share_1')
        self.assertEqual(key, 'server-1/share_1')

    @patch('src.handlers.smb_handler.subprocess.run')
    def test_unmount_share_success(self, mock_run):
        """Test successful unmount"""
        mock_run.return_value = Mock(returncode=0, stderr='', stdout='')
        result = unmount_share('/mnt/test')
        self.assertTrue(result)
        mock_run.assert_called_once()

    @patch('src.handlers.smb_handler.subprocess.run')
    def test_unmount_share_failure(self, mock_run):
        """Test failed unmount"""
        mock_run.return_value = Mock(
            returncode=32, stderr='Device or resource busy', stdout=''
        )
        result = unmount_share('/mnt/test')
        self.assertFalse(result)

    @patch('src.handlers.smb_handler.subprocess.run')
    def test_unmount_share_timeout(self, mock_run):
        """Test unmount timeout"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('umount', 10)
        result = unmount_share('/mnt/test')
        self.assertFalse(result)


class TestSMBHandlerListServers(unittest.TestCase):
    """Test SMB server listing endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    @patch('src.handlers.smb_handler.list_all_servers')
    def test_list_servers_success(self, mock_list):
        """Test listing servers successfully"""
        mock_list.return_value = [
            {'host': 'server1', 'type': 'workstation'},
            {'host': 'server2', 'type': 'server'}
        ]

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_list_servers())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['status'], 'success')
        self.assertEqual(len(response.json_data['data']['servers']), 2)

    @patch('src.handlers.smb_handler.list_all_servers')
    def test_list_servers_empty(self, mock_list):
        """Test listing when no servers found"""
        mock_list.return_value = []

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_list_servers())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['data']['count'], 0)

    @patch('src.handlers.smb_handler.list_all_servers')
    def test_list_servers_error(self, mock_list):
        """Test error listing servers"""
        mock_list.side_effect = OSError('Network error')

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_list_servers())

        self.assertEqual(status, 500)
        self.assertEqual(response.json_data['status'], 'error')


class TestSMBHandlerTestConnection(unittest.TestCase):
    """Test SMB connection testing endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    @patch('src.handlers.smb_handler.check_smb_connection')
    def test_test_connection_success(self, mock_check):
        """Test successful connection"""
        mock_check.return_value = (True, None)
        mock_request = MagicMock()
        mock_request.get_json.return_value = {
            'username': 'user',
            'password': 'pass'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_test_connection('server1'))

        self.assertEqual(status, 200)
        self.assertTrue(response.json_data['data']['connected'])

    @patch('src.handlers.smb_handler.check_smb_connection')
    def test_test_connection_failure(self, mock_check):
        """Test failed connection"""
        mock_check.return_value = (False, 'Authentication failed')
        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_test_connection('server1'))

        self.assertEqual(status, 200)
        self.assertFalse(response.json_data['data']['connected'])

    def test_test_connection_missing_auth(self):
        """Test connection without credentials"""
        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch('src.handlers.smb_handler.request', mock_request):
            with patch('src.handlers.smb_handler.check_smb_connection') as mock_check:
                mock_check.return_value = (True, None)
                response, status = get_response(self.handler.handle_test_connection('server1'))

        self.assertEqual(status, 200)


class TestSMBHandlerListShares(unittest.TestCase):
    """Test SMB share listing endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    @patch('src.handlers.smb_handler.list_smb_shares')
    def test_list_shares_success(self, mock_list):
        """Test listing shares successfully"""
        mock_list.return_value = (
            [
                {'name': 'share1', 'type': 'Disk', 'comment': 'Test share'},
                {'name': 'share2', 'type': 'IPC', 'comment': ''}
            ],
            'SMBv2'
        )
        mock_request = MagicMock()
        mock_request.get_json.return_value = {'server': 'server1'}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_list_shares())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['status'], 'success')
        self.assertEqual(len(response.json_data['data']['shares']), 2)

    @patch('src.handlers.smb_handler.list_smb_shares')
    def test_list_shares_no_server(self, mock_list):
        """Test listing shares without server parameter"""
        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_list_shares())

        self.assertEqual(status, 400)
        self.assertEqual(response.json_data['status'], 'error')
        self.assertIn('server', response.json_data['message'].lower())

    @patch('src.handlers.smb_handler.list_smb_shares')
    def test_list_shares_detailed(self, mock_list):
        """Test listing shares with detailed info"""
        mock_list.return_value = (
            [{'name': 'share1', 'type': 'Disk', 'comment': 'Test',
              'size': '100GB', 'available': '50GB'}],
            None
        )
        mock_request = MagicMock()
        mock_request.get_json.return_value = {'server': 'server1', 'detailed': True}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_list_shares())

        self.assertEqual(status, 200)
        self.assertIn('size', response.json_data['data']['shares'][0])

    @patch('src.handlers.smb_handler.list_smb_shares')
    def test_list_shares_exception(self, mock_list):
        """Test handling exception in list_shares"""
        mock_list.side_effect = OSError('Connection refused')
        mock_request = MagicMock()
        mock_request.get_json.return_value = {'server': 'server1'}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_list_shares())

        self.assertEqual(status, 500)
        self.assertEqual(response.json_data['status'], 'error')


class TestSMBHandlerListMounts(unittest.TestCase):
    """Test SMB mount listing endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    @patch('src.handlers.smb_handler.list_configured_mounts')
    def test_list_mounts_success(self, mock_list):
        """Test listing mounts successfully"""
        mock_list.return_value = [
            {'server': 'server1', 'share': 'share1', 'mountpoint': '/mnt/test1',
             'mounted': True},
            {'server': 'server2', 'share': 'share2', 'mountpoint': '/mnt/test2',
             'mounted': False}
        ]

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_list_mounts())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['data']['summary']['total'], 2)
        self.assertEqual(response.json_data['data']['summary']['mounted'], 1)
        self.assertEqual(response.json_data['data']['summary']['unmounted'], 1)

    @patch('src.handlers.smb_handler.list_configured_mounts')
    def test_list_mounts_empty(self, mock_list):
        """Test listing when no mounts configured"""
        mock_list.return_value = []

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_list_mounts())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['data']['count'], 0)


class TestSMBHandlerManageMount(unittest.TestCase):
    """Test SMB mount configuration endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    def test_manage_mount_not_json(self):
        """Test with non-JSON content type"""
        mock_request = MagicMock()
        mock_request.is_json = False

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 400)
        self.assertEqual(response.json_data['status'], 'error')

    def test_manage_mount_missing_action(self):
        """Test with missing action parameter"""
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {'server': 'server1'}

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 400)
        self.assertEqual(response.json_data['status'], 'error')

    def test_manage_mount_invalid_action(self):
        """Test with invalid action"""
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'action': 'invalid',
            'server': 'server1',
            'share': 'share1'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 400)
        self.assertEqual(response.json_data['status'], 'error')

    @patch('src.handlers.smb_handler.add_mount_config')
    def test_manage_mount_add_success(self, mock_add):
        """Test adding mount configuration"""
        mock_add.return_value = (True, None)
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'action': 'add',
            'server': 'server1',
            'share': 'share1',
            'mountpoint': '/mnt/test'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['status'], 'success')

    @patch('src.handlers.smb_handler.add_mount_config')
    def test_manage_mount_add_exists(self, mock_add):
        """Test adding mount that already exists"""
        mock_add.return_value = (False, 'already exists')
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'action': 'add',
            'server': 'server1',
            'share': 'share1'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 400)
        self.assertEqual(response.json_data['status'], 'error')

    @patch('src.handlers.smb_handler.remove_mount_config')
    def test_manage_mount_remove_success(self, mock_remove):
        """Test removing mount configuration"""
        mock_remove.return_value = (True, '/mnt/test')
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'action': 'remove',
            'server': 'server1',
            'share': 'share1'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['status'], 'success')

    @patch('src.handlers.smb_handler.remove_mount_config')
    def test_manage_mount_remove_not_found(self, mock_remove):
        """Test removing non-existent mount"""
        mock_remove.return_value = (False, None)
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            'action': 'remove',
            'server': 'server1',
            'share': 'share1'
        }

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 404)
        self.assertEqual(response.json_data['status'], 'error')


class TestSMBHandlerMountAll(unittest.TestCase):
    """Test mount all shares endpoint"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    @patch('src.handlers.smb_handler.subprocess.run')
    @patch('src.handlers.smb_handler.list_configured_mounts')
    @patch('src.handlers.smb_handler.load_mount_state')
    def test_mount_all_success(self, mock_load, mock_list, mock_run):
        """Test mounting all shares successfully"""
        mock_load.return_value = {}
        mock_list.return_value = [
            {'server': 'server1', 'share': 'share1', 'mountpoint': '/mnt/test1', 'id': 'id1'}
        ]
        mock_run.return_value = Mock(returncode=0, stderr='', stdout='')

        with patch('src.handlers.smb_handler.request', MagicMock()):
            with patch.object(self.handler, '_trigger_mpd_reconcile') as mock_mpd:
                mock_mpd.return_value = {'status': 'success'}
                response, status = get_response(self.handler.handle_mount_all_samba())

        self.assertEqual(status, 200)
        self.assertEqual(response.json_data['status'], 'success')

    @patch('src.handlers.smb_handler.subprocess.run')
    @patch('src.handlers.smb_handler.list_configured_mounts')
    @patch('src.handlers.smb_handler.load_mount_state')
    def test_mount_all_service_failure(self, mock_load, mock_list, mock_run):
        """Test mount all with service restart failure"""
        mock_load.return_value = {}
        mock_list.return_value = []
        mock_run.return_value = Mock(returncode=1, stderr='Failed', stdout='')

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_mount_all_samba())

        self.assertEqual(status, 500)
        self.assertEqual(response.json_data['status'], 'error')

    @patch('src.handlers.smb_handler.subprocess.run')
    @patch('src.handlers.smb_handler.list_configured_mounts')
    @patch('src.handlers.smb_handler.load_mount_state')
    def test_mount_all_timeout(self, mock_load, mock_list, mock_run):
        """Test mount all with service timeout"""
        import subprocess
        mock_load.return_value = {}
        mock_list.return_value = []
        mock_run.side_effect = subprocess.TimeoutExpired('systemctl', 30)

        with patch('src.handlers.smb_handler.request', MagicMock()):
            response, status = get_response(self.handler.handle_mount_all_samba())

        self.assertEqual(status, 500)
        self.assertEqual(response.json_data['status'], 'error')

    @patch('src.handlers.smb_handler.subprocess.run')
    @patch('src.handlers.smb_handler.list_configured_mounts')
    @patch('src.handlers.smb_handler.load_mount_state')
    def test_mount_all_with_cleanup(self, mock_load, mock_list, mock_run):
        """Test mount all with unmounting removed shares"""
        mock_run.return_value = Mock(returncode=0, stderr='', stdout='')
        # Previous state has share that's no longer configured
        mock_load.return_value = {'server1/share1': '/mnt/old'}
        mock_list.return_value = []

        with patch('src.handlers.smb_handler.request', MagicMock()):
            with patch('src.handlers.smb_handler.unmount_share', return_value=True) as mock_unmount:
                with patch.object(self.handler, '_trigger_mpd_reconcile') as mock_mpd:
                    mock_mpd.return_value = {'status': 'success'}
                    response, status = get_response(self.handler.handle_mount_all_samba())

        self.assertEqual(status, 200)
        # Should have attempted cleanup
        mock_unmount.assert_called_once()


class TestSMBHandlerEdgeCases(unittest.TestCase):
    """Test error handling and edge cases"""

    def setUp(self):
        """Create handler"""
        self.handler = SMBHandler()

    def test_handle_test_connection_url_override(self):
        """Test connection with server override from body"""
        mock_request = MagicMock()
        mock_request.get_json.return_value = {'server': 'override-server'}

        with patch('src.handlers.smb_handler.request', mock_request):
            with patch('src.handlers.smb_handler.check_smb_connection') as mock_check:
                mock_check.return_value = (True, None)
                response, status = get_response(self.handler.handle_test_connection('url-server'))

        # Should use server from body
        mock_check.assert_called_once()
        call_args = mock_check.call_args
        self.assertEqual(call_args.kwargs['server'], 'override-server')

    @patch('src.handlers.smb_handler.subprocess.run')
    def test_manage_mount_exception(self, mock_run):
        """Test exception handling in manage_mount"""
        mock_request = MagicMock()
        mock_request.is_json = True
        mock_request.get_json.side_effect = Exception('JSON parse error')

        with patch('src.handlers.smb_handler.request', mock_request):
            response, status = get_response(self.handler.handle_manage_mount())

        self.assertEqual(status, 500)
        self.assertEqual(response.json_data['status'], 'error')


if __name__ == '__main__':
    unittest.main()
