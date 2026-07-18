#!/usr/bin/env python3
"""
Regression tests for ble_provisioning module

Tests the BLE WiFi provisioning server functionality for:
- Device identity and network status retrieval
- JSON serialization of responses
- WiFi scan and connection handling
- BLE control message parsing
- Network connectivity checks
- CLI argument parsing
- Logging setup
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Mock the bless module and other dependencies before importing anything from src
sys.modules['bless'] = MagicMock()
sys.modules['bless.backends'] = MagicMock()
sys.modules['bless.backends.bluezdbus'] = MagicMock()
sys.modules['bless.backends.bluezdbus.server'] = MagicMock()
sys.modules['bless.backends.bluezdbus.characteristic'] = MagicMock()
sys.modules['bless.backends.attribute'] = MagicMock()
sys.modules['bless.backends.characteristic'] = MagicMock()

sys.modules['netifaces'] = MagicMock()

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock the src modules that have external dependencies
sys.modules['src.wifi'] = MagicMock()
sys.modules['src.network'] = MagicMock()

from src.ble_provisioning import (  # noqa: E402
    BLEProvisioningServer,
    has_network_connectivity,
    setup_logging,
    main,
)


class TestBLEProvisioningServer:
    """Test cases for BLEProvisioningServer class"""

    @pytest.fixture
    def server(self):
        """Fixture providing a BLEProvisioningServer instance"""
        return BLEProvisioningServer()

    def test_init_creates_instance(self, server):
        """Test that BLEProvisioningServer initializes correctly"""
        assert server.server is None
        assert server.loop is None
        assert server._scan_results == []
        assert server._connect_status == {
            "state": "idle",
            "ssid": "",
            "error": "",
        }
        assert server._shutdown_requested is False

    @patch("src.ble_provisioning.platform.node")
    def test_get_hostname(self, mock_node, server):
        """Test hostname retrieval"""
        mock_node.return_value = "hifiberry-test"
        
        hostname = server._get_hostname()
        
        assert hostname == "hifiberry-test"
        mock_node.assert_called_once()

    @patch("src.ble_provisioning.platform.node")
    def test_get_device_identity_success(self, mock_node, server):
        """Test device identity retrieval with all components"""
        mock_node.return_value = "hifiberry-01"
        
        with patch("src.ble_provisioning.sys"):
            identity_bytes = server._get_device_identity()
        
        data = json.loads(identity_bytes.decode("utf-8"))
        assert data["hostname"] == "hifiberry-01"
        assert "model" in data
        assert "version" in data

    @patch("src.ble_provisioning.platform.node")
    def test_get_device_identity_minimal(self, mock_node, server):
        """Test device identity with missing optional components"""
        mock_node.return_value = "test-host"
        
        # Mock the version import to return nothing
        with patch.dict('sys.modules', {'src._version': None}):
            identity_bytes = server._get_device_identity()
        
        data = json.loads(identity_bytes.decode("utf-8"))
        assert data["hostname"] == "test-host"
        assert "model" in data
        assert "version" in data

    @patch("src.ble_provisioning.network.get_network_config")
    @patch("src.ble_provisioning.wifi.get_current_connection")
    @patch("src.ble_provisioning.platform.node")
    def test_get_network_status_no_interfaces(
        self, mock_node, mock_get_conn, mock_get_config, server
    ):
        """Test network status with no interfaces"""
        mock_node.return_value = "test-host"
        mock_get_config.return_value = {
            "hostname": "test-host",
            "interfaces": []
        }
        
        status_bytes = server._get_network_status()
        
        data = json.loads(status_bytes.decode("utf-8"))
        assert data["wifi_connected"] is False
        assert data["eth_connected"] is False
        assert data["hostname"] == "test-host"

    @patch("src.ble_provisioning.network.get_network_config")
    @patch("src.ble_provisioning.wifi.get_current_connection")
    @patch("src.ble_provisioning.platform.node")
    def test_get_network_status_wifi_connected(
        self, mock_node, mock_get_conn, mock_get_config, server
    ):
        """Test network status with WiFi connected"""
        mock_node.return_value = "test-host"
        mock_get_config.return_value = {
            "hostname": "test-host",
            "interfaces": [
                {
                    "name": "wlan0",
                    "type": "wireless",
                    "ipv4": "192.168.1.100"
                }
            ]
        }
        mock_get_conn.return_value = {"ssid": "TestNetwork"}
        
        status_bytes = server._get_network_status()
        
        data = json.loads(status_bytes.decode("utf-8"))
        assert data["wifi_connected"] is True
        assert data["wifi_ip"] == "192.168.1.100"
        assert data["wifi_ssid"] == "TestNetwork"

    @patch("src.ble_provisioning.network.get_network_config")
    @patch("src.ble_provisioning.wifi.get_current_connection")
    @patch("src.ble_provisioning.platform.node")
    def test_get_network_status_eth_connected(
        self, mock_node, mock_get_conn, mock_get_config, server
    ):
        """Test network status with Ethernet connected"""
        mock_node.return_value = "test-host"
        mock_get_config.return_value = {
            "hostname": "test-host",
            "interfaces": [
                {
                    "name": "eth0",
                    "type": "wired",
                    "ipv4": "10.0.0.50"
                }
            ]
        }
        
        status_bytes = server._get_network_status()
        
        data = json.loads(status_bytes.decode("utf-8"))
        assert data["eth_connected"] is True
        assert data["eth_ip"] == "10.0.0.50"

    @patch("src.ble_provisioning.network.get_network_config")
    def test_get_network_status_error_handling(self, mock_get_config, server):
        """Test network status with error retrieving config"""
        mock_get_config.side_effect = IOError("Connection error")
        
        status_bytes = server._get_network_status()
        
        data = json.loads(status_bytes.decode("utf-8"))
        # When there's an error, network status should still return valid structure
        assert data["wifi_connected"] is False
        assert data["eth_connected"] is False

    def test_get_scan_results_bytes_empty(self, server):
        """Test scan results bytes with empty results"""
        server._scan_results = []
        
        results_bytes = server._get_scan_results_bytes()
        
        data = json.loads(results_bytes.decode("utf-8"))
        assert data == []

    def test_get_scan_results_bytes_with_networks(self, server):
        """Test scan results bytes with WiFi networks"""
        server._scan_results = [
            {"ssid": "Network1", "signal": -50, "security": "WPA2"},
            {"ssid": "Network2", "signal": -70, "security": "Open"},
        ]
        
        results_bytes = server._get_scan_results_bytes()
        
        data = json.loads(results_bytes.decode("utf-8"))
        assert len(data) == 2
        assert data[0]["ssid"] == "Network1"
        assert data[1]["signal"] == -70

    def test_get_connect_status_bytes_idle(self, server):
        """Test connect status bytes in idle state"""
        status_bytes = server._get_connect_status_bytes()
        
        data = json.loads(status_bytes.decode("utf-8"))
        assert data["state"] == "idle"
        assert data["ssid"] == ""
        assert data["error"] == ""

    def test_get_connect_status_bytes_connecting(self, server):
        """Test connect status bytes while connecting"""
        server._connect_status = {
            "state": "connecting",
            "ssid": "MyNetwork",
            "error": ""
        }
        
        status_bytes = server._get_connect_status_bytes()
        
        data = json.loads(status_bytes.decode("utf-8"))
        assert data["state"] == "connecting"
        assert data["ssid"] == "MyNetwork"

    def test_handle_scan_trigger_with_trigger_byte(self, server):
        """Test WiFi scan trigger with 0xFF byte"""
        with patch("asyncio.ensure_future") as mock_future:
            mock_future.side_effect = lambda coro: coro.close()
            server._handle_scan_trigger(bytearray(b"\xFF"))
        
        # Should schedule the scan
        mock_future.assert_called_once()

    def test_handle_scan_trigger_with_empty_value(self, server):
        """Test WiFi scan trigger with empty value"""
        with patch("asyncio.ensure_future") as mock_future:
            server._handle_scan_trigger(bytearray(b""))
        
        # Should not schedule the scan
        mock_future.assert_not_called()

    def test_handle_wifi_connect_valid_payload(self, server):
        """Test WiFi connect with valid JSON payload"""
        payload = json.dumps({
            "ssid": "TestNetwork",
            "passphrase": "password123"
        }).encode("utf-8")
        
        with patch("asyncio.ensure_future") as mock_future:
            mock_future.side_effect = lambda coro: coro.close()
            server._handle_wifi_connect(bytearray(payload))
        
        assert server._connect_status["state"] == "connecting"
        assert server._connect_status["ssid"] == "TestNetwork"
        mock_future.assert_called_once()

    def test_handle_wifi_connect_empty_ssid(self, server):
        """Test WiFi connect with empty SSID"""
        payload = json.dumps({
            "ssid": "",
            "passphrase": "password"
        }).encode("utf-8")
        
        with patch("asyncio.ensure_future") as mock_future:
            server._handle_wifi_connect(bytearray(payload))
        
        # Should not attempt connection
        mock_future.assert_not_called()

    def test_handle_wifi_connect_invalid_json(self, server):
        """Test WiFi connect with invalid JSON"""
        invalid_json = b"{ invalid json"
        
        server._handle_wifi_connect(bytearray(invalid_json))
        
        assert server._connect_status["state"] == "failed"
        assert server._connect_status["error"] != ""

    def test_handle_ble_control_stop_ble(self, server):
        """Test BLE control stop command"""
        payload = json.dumps({
            "action": "stop_ble"
        }).encode("utf-8")
        
        mock_loop = MagicMock()
        server.loop = mock_loop
        
        server._handle_ble_control(bytearray(payload))
        
        assert server._shutdown_requested is True
        mock_loop.call_soon_threadsafe.assert_called_once()

    def test_handle_ble_control_unknown_action(self, server):
        """Test BLE control with unknown action"""
        payload = json.dumps({
            "action": "unknown_action"
        }).encode("utf-8")
        
        server._handle_ble_control(bytearray(payload))
        
        # Should not set shutdown flag
        assert server._shutdown_requested is False

    def test_handle_ble_control_invalid_json(self, server):
        """Test BLE control with invalid JSON"""
        invalid_json = b"{ invalid }"
        
        # Should not raise exception
        server._handle_ble_control(bytearray(invalid_json))
        assert server._shutdown_requested is False


class TestNetworkConnectivity:
    """Test cases for network connectivity check"""

    @patch("src.ble_provisioning.network.list_physical_interfaces")
    def test_has_network_connectivity_true(self, mock_interfaces):
        """Test network connectivity detection when connected"""
        mock_interfaces.return_value = [
            {"name": "eth0", "ipv4": "192.168.1.100"},
            {"name": "wlan0", "ipv4": None}
        ]
        
        result = has_network_connectivity()
        
        assert result is True

    @patch("src.ble_provisioning.network.list_physical_interfaces")
    def test_has_network_connectivity_false(self, mock_interfaces):
        """Test network connectivity detection when not connected"""
        mock_interfaces.return_value = [
            {"name": "eth0", "ipv4": None},
            {"name": "wlan0", "ipv4": None}
        ]
        
        result = has_network_connectivity()
        
        assert result is False

    @patch("src.ble_provisioning.network.list_physical_interfaces")
    def test_has_network_connectivity_error(self, mock_interfaces):
        """Test network connectivity detection with error"""
        mock_interfaces.side_effect = IOError("Error reading interfaces")
        
        result = has_network_connectivity()
        
        assert result is False

    @patch("src.ble_provisioning.network.list_physical_interfaces")
    def test_has_network_connectivity_empty_list(self, mock_interfaces):
        """Test network connectivity detection with no interfaces"""
        mock_interfaces.return_value = []
        
        result = has_network_connectivity()
        
        assert result is False


class TestSetupLogging:
    """Test cases for setup_logging function"""

    @patch("src.ble_provisioning.logging.getLogger")
    @patch("src.ble_provisioning.logging.StreamHandler")
    @patch("src.ble_provisioning.logging.Formatter")
    def test_setup_logging_normal(self, mock_formatter, mock_handler, mock_logger):
        """Test logging setup with normal verbosity"""
        mock_root_logger = MagicMock()
        mock_logger.return_value = mock_root_logger
        
        setup_logging(verbose=False)
        
        mock_root_logger.setLevel.assert_called()

    @patch("src.ble_provisioning.logging.getLogger")
    @patch("src.ble_provisioning.logging.StreamHandler")
    @patch("src.ble_provisioning.logging.Formatter")
    def test_setup_logging_verbose(self, mock_formatter, mock_handler, mock_logger):
        """Test logging setup with verbose flag"""
        mock_root_logger = MagicMock()
        mock_logger.return_value = mock_root_logger
        
        setup_logging(verbose=True)
        
        mock_root_logger.setLevel.assert_called()


class TestMainCLI:
    """Test cases for main CLI function"""

    @patch("src.ble_provisioning.has_network_connectivity")
    @patch("sys.exit")
    def test_main_check_network_no_connectivity(self, mock_exit, mock_has_conn):
        """Test check-network when no network connectivity"""
        mock_has_conn.return_value = False
        
        with patch("sys.argv", ["ble-provisioning", "--check-network"]):
            main()
        
        mock_exit.assert_called_with(0)

    @patch("src.ble_provisioning.has_network_connectivity")
    @patch("sys.exit")
    def test_main_check_network_with_connectivity(self, mock_exit, mock_has_conn):
        """Test check-network when network is connected"""
        mock_has_conn.return_value = True
        
        with patch("sys.argv", ["ble-provisioning", "--check-network"]):
            main()
        
        mock_exit.assert_called_with(1)

    @patch("src.ble_provisioning.subprocess.run")
    @patch("sys.exit")
    def test_main_stop_service(self, mock_exit, mock_run):
        """Test stop action"""
        mock_run.return_value = MagicMock(returncode=0)
        
        with patch("sys.argv", ["ble-provisioning", "--stop"]):
            main()
        
        mock_run.assert_called_once()
        mock_exit.assert_called_with(0)

    @patch("sys.argv", ["ble-provisioning"])
    def test_main_no_action_required(self):
        """Test main with no action specified"""
        # Should exit with error due to mutually exclusive group requirement
        with pytest.raises(SystemExit):
            main()

    @patch("src.ble_provisioning.setup_logging")
    def test_main_verbose_flag(self, mock_setup_logging):
        """Test that verbose flag is processed"""
        with patch("sys.argv", ["ble-provisioning", "--check-network", "-v"]):
            with patch("src.ble_provisioning.has_network_connectivity", return_value=False):
                with patch("sys.exit"):
                    main()
        
        mock_setup_logging.assert_called()
