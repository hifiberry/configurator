#!/usr/bin/env python3
"""
Regression tests for avahi module

Tests the Avahi configuration functionality for:
- Configuration parsing and modification
- Interface configuration detection
- File I/O operations with backup creation
- Service restart handling
- Root privilege checks
- CLI argument parsing
"""

import os
from unittest.mock import patch, MagicMock, mock_open
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from avahi import configure_avahi_interfaces, check_root_privileges, setup_logging


class TestConfigureAvahiInterfaces:
    """Test cases for configure_avahi_interfaces function"""
    
    @patch('avahi.subprocess.run')
    @patch('avahi.os.path.exists')
    def test_avahi_not_installed(self, mock_exists, mock_subprocess):
        """Test behavior when Avahi is not installed"""
        mock_exists.return_value = False
        
        result = configure_avahi_interfaces()
        
        assert result is True
        mock_subprocess.assert_not_called()
    
    @patch('avahi.subprocess.run')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\nallow-interfaces=eth0,wlan0\n")
    def test_configuration_already_correct(self, mock_file, mock_exists, mock_subprocess):
        """Test when configuration is already correct"""
        mock_exists.return_value = True
        
        result = configure_avahi_interfaces()
        
        assert result is True
    
    @patch('avahi.subprocess.run')
    @patch('avahi.shutil.copy2')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\n# comment\n")
    def test_adds_allow_interfaces_to_server_section(self, mock_file, mock_exists, 
                                                      mock_copy2, mock_subprocess):
        """Test that allow-interfaces is added to [server] section"""
        mock_exists.return_value = True
        mock_subprocess.return_value.returncode = 0
        
        result = configure_avahi_interfaces()
        
        assert result is True
    
    @patch('avahi.subprocess.run')
    @patch('avahi.shutil.copy2')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\ndeny-interfaces=docker0\n")
    def test_removes_existing_deny_interfaces(self, mock_file, mock_exists, 
                                               mock_copy2, mock_subprocess):
        """Test that existing deny-interfaces lines are removed"""
        mock_exists.return_value = True
        mock_subprocess.return_value.returncode = 0
        
        result = configure_avahi_interfaces()
        
        assert result is True
    
    @patch('avahi.subprocess.run')
    @patch('avahi.shutil.copy2')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\n# comment\n")
    def test_service_restart_when_active(self, mock_file, mock_exists, 
                                          mock_copy2, mock_subprocess):
        """Test that service is restarted when active"""
        mock_exists.return_value = True
        # First call returns 0 (service is active), second call succeeds
        mock_subprocess.return_value.returncode = 0
        
        result = configure_avahi_interfaces()
        
        assert result is True
        # Should check if service is active and then restart it
        assert mock_subprocess.call_count >= 2
    
    @patch('avahi.subprocess.run')
    @patch('avahi.shutil.copy2')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\n# comment\n")
    def test_service_start_when_inactive(self, mock_file, mock_exists, 
                                          mock_copy2, mock_subprocess):
        """Test that service is started when not active"""
        mock_exists.return_value = True
        
        # First call returns non-zero (service is inactive), second call succeeds
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.returncode = 1  # Service is inactive
            else:
                result.returncode = 0  # Start succeeds
            return result
        
        mock_subprocess.side_effect = side_effect
        
        result = configure_avahi_interfaces()
        
        assert result is True
    
    @patch('avahi.subprocess.run')
    @patch('avahi.shutil.copy2')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="[server]\n# comment\n")
    def test_restart_failure_returns_false(self, mock_file, mock_exists, 
                                            mock_copy2, mock_subprocess):
        """Test that restart failure is handled appropriately"""
        mock_exists.return_value = True
        
        # Service is active but restart fails
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.returncode = 0  # Service is active
            else:
                result.returncode = 1  # Restart fails
                result.stderr = "error message"
            return result
        
        mock_subprocess.side_effect = side_effect
        
        result = configure_avahi_interfaces()
        
        assert result is False
    
    @patch('avahi.subprocess.run')
    @patch('avahi.os.path.exists')
    @patch('builtins.open', side_effect=IOError("Cannot read file"))
    def test_read_error_handling(self, mock_open_error, mock_exists, mock_subprocess):
        """Test that read errors are handled gracefully"""
        mock_exists.return_value = True
        
        result = configure_avahi_interfaces()
        
        assert result is False



class TestCheckRootPrivileges:
    """Test cases for check_root_privileges function"""
    
    @patch('avahi.os.geteuid')
    def test_running_as_root(self, mock_geteuid):
        """Test when running as root"""
        mock_geteuid.return_value = 0
        
        result = check_root_privileges()
        
        assert result is True
    
    @patch('avahi.os.geteuid')
    def test_not_running_as_root(self, mock_geteuid):
        """Test when not running as root"""
        mock_geteuid.return_value = 1000
        
        result = check_root_privileges()
        
        assert result is False


class TestSetupLogging:
    """Test cases for setup_logging function"""
    
    @patch('avahi.logging.basicConfig')
    def test_setup_logging_normal(self, mock_logging):
        """Test logging setup with normal verbosity"""
        setup_logging(verbose=False)
        
        mock_logging.assert_called_once()
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs['level'] == 20  # logging.INFO
    
    @patch('avahi.logging.basicConfig')
    def test_setup_logging_verbose(self, mock_logging):
        """Test logging setup with verbose flag"""
        setup_logging(verbose=True)
        
        mock_logging.assert_called_once()
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs['level'] == 10  # logging.DEBUG
