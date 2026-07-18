import sys
import pytest
import tempfile
import configparser
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Create real exception classes before mocking
class MockDBusError(Exception):
    """Mock DBusError exception class."""
    pass

# Mock dbus_fast before importing bluetooth module
mock_dbus_fast = MagicMock()
mock_dbus_fast.DBusError = MockDBusError
mock_dbus_fast.BusType = MagicMock()
mock_dbus_fast.BusType.SYSTEM = "system"

sys.modules["dbus_fast"] = mock_dbus_fast
sys.modules["dbus_fast.aio"] = MagicMock()


class TestConfigFileManager:
    """Tests for ConfigFileManager class."""

    def test_init_creates_config_file_if_not_exists(self):
        """Test that ConfigFileManager creates config file if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                assert config_path.exists()
                assert cfm.capability == "NoInputNoOutput"

    def test_init_loads_existing_config(self):
        """Test that ConfigFileManager loads existing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            config_path.write_text(
                "[Bluetooth]\n"
                "capability=KeyboardDisplay\n"
                "discoverable=False\n"
                "pairable=True\n"
            )
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                assert cfm.capability == "KeyboardDisplay"
                assert cfm.discoverable is False
                assert cfm.pairable is True

    def test_create_config_file(self):
        """Test config file creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                cfm.create_config_file()
                
                assert config_path.exists()
                content = config_path.read_text()
                assert "[Bluetooth]" in content
                assert "capability=NoInputNoOutput" in content

    def test_load_config_values_with_defaults(self):
        """Test loading config values with default fallbacks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            config_path.write_text(
                "[Bluetooth]\n"
                "discoverable=True\n"
                "discoverable_timeout=0\n"
                "pairable=True\n"
                "pairable_timeout=0\n"
            )
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                cfm.load_config_values()
                
                assert cfm.capability == "KeyboardDisplay"
                assert cfm.discoverable is True
                assert cfm.pairable is True
                assert cfm.discoverable_timeout == 0
                assert cfm.pairable_timeout == 0

    def test_set_config_value(self):
        """Test setting a config value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                cfm.set_config_value("Bluetooth", "capability", "NoInputNoOutput")
                
                # Reload and verify
                config = configparser.ConfigParser()
                config.read(config_path)
                assert config.get("Bluetooth", "capability") == "NoInputNoOutput"

    def test_set_config_value_creates_section(self):
        """Test that setting config value creates section if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            config_path.write_text("[Bluetooth]\n")
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                cfm.set_config_value("NewSection", "key", "value")
                
                config = configparser.ConfigParser()
                config.read(config_path)
                assert config.get("NewSection", "key") == "value"

    def test_set_config_value_error_handling(self):
        """Test error handling when setting config value fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import ConfigFileManager
                
                cfm = ConfigFileManager()
                
                # Mock open to raise exception
                with patch("builtins.open", side_effect=IOError("Permission denied")):
                    cfm.set_config_value("Bluetooth", "key", "value")
                    # Should not raise, just log error


class TestGetBluetoothSettings:
    """Tests for get_bluetooth_settings() function."""

    def test_get_bluetooth_settings_success(self):
        """Test retrieving bluetooth settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            config_path.write_text(
                "[Bluetooth]\n"
                "capability=KeyboardDisplay\n"
                "discoverable=True\n"
                "discoverable_timeout=120\n"
                "pairable=False\n"
                "pairable_timeout=60\n"
            )
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import get_bluetooth_settings
                
                settings = get_bluetooth_settings()
                
                assert settings["capability"] == "KeyboardDisplay"
                assert settings["discoverable"] is True
                assert settings["discoverableTimeout"] == 120
                assert settings["pairable"] is False
                assert settings["pairableTimeout"] == 60

    def test_get_bluetooth_settings_returns_dict(self):
        """Test that get_bluetooth_settings returns a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import get_bluetooth_settings
                
                settings = get_bluetooth_settings()
                
                assert isinstance(settings, dict)
                assert "capability" in settings
                assert "discoverable" in settings
                assert "pairable" in settings


class TestSetBluetoothSettings:
    """Tests for set_bluetooth_settings() function."""

    def test_set_bluetooth_settings_single_value(self):
        """Test setting a single bluetooth setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import set_bluetooth_settings, get_bluetooth_settings
                
                set_bluetooth_settings({"capability": "NoInputNoOutput"})
                settings = get_bluetooth_settings()
                
                assert settings["capability"] == "NoInputNoOutput"

    def test_set_bluetooth_settings_multiple_values(self):
        """Test setting multiple bluetooth settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import set_bluetooth_settings, get_bluetooth_settings
                
                set_bluetooth_settings({
                    "capability": "Keyboard",
                    "discoverable": False,
                    "pairable": True,
                })
                settings = get_bluetooth_settings()
                
                assert settings["capability"] == "Keyboard"
                assert settings["discoverable"] is False
                assert settings["pairable"] is True

    def test_set_bluetooth_settings_empty_timeout_becomes_zero(self):
        """Test that empty timeout values become '0'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import set_bluetooth_settings, get_bluetooth_settings
                
                set_bluetooth_settings({"discoverable_timeout": ""})
                settings = get_bluetooth_settings()
                
                assert settings["discoverableTimeout"] == 0

    def test_set_bluetooth_settings_returns_updated_settings(self):
        """Test that set_bluetooth_settings returns the updated settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import set_bluetooth_settings
                
                result = set_bluetooth_settings({"capability": "Display"})
                
                assert isinstance(result, dict)
                assert result["capability"] == "Display"

    def test_set_bluetooth_settings_ignores_invalid_keys(self):
        """Test that invalid keys are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bluetooth.conf"
            
            with patch("src.bluetooth.ConfigFileManager.config_path", config_path):
                from src.bluetooth import set_bluetooth_settings, get_bluetooth_settings
                
                # Should not raise error for invalid keys
                set_bluetooth_settings({
                    "capability": "Display",
                    "invalid_key": "should_be_ignored",
                })
                settings = get_bluetooth_settings()
                
                assert settings["capability"] == "Display"


class TestGetPairedDevices:
    """Tests for get_paired_devices() async function."""

    @pytest.mark.asyncio
    async def test_get_paired_devices_success(self):
        """Test successful retrieval of paired devices."""
        # Mock dbus-fast components
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_proxy_object = MagicMock()
        
        # Mock return values
        mock_devices = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                "org.bluez.Device1": {
                    "Name": "TestDevice",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Paired": True,
                    "Connected": True,
                    "Trusted": True,
                }
            },
            "/org/bluez/hci0/dev_11_22_33_44_55_66": {
                "org.bluez.Device1": {
                    "Name": "AnotherDevice",
                    "Address": "11:22:33:44:55:66",
                    "Paired": True,
                    "Connected": False,
                    "Trusted": False,
                }
            }
        }
        
        # Setup mock return values
        async def mock_get_managed_objects():
            return mock_devices
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_bus.get_proxy_object.return_value = mock_proxy_object
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            devices = await get_paired_devices()
            
            assert len(devices) == 2
            assert devices[0]["name"] == "TestDevice"
            assert devices[0]["address"] == "AA:BB:CC:DD:EE:FF"
            assert devices[0]["connected"] is True
            assert devices[1]["name"] == "AnotherDevice"
            assert devices[1]["address"] == "11:22:33:44:55:66"
            assert devices[1]["connected"] is False

    @pytest.mark.asyncio
    async def test_get_paired_devices_empty_list(self):
        """Test get_paired_devices with no paired devices."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_proxy_object = MagicMock()
        
        async def mock_get_managed_objects():
            return {}
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_bus.get_proxy_object.return_value = mock_proxy_object
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            devices = await get_paired_devices()
            
            assert devices == []

    @pytest.mark.asyncio
    async def test_get_paired_devices_filters_unpaired(self):
        """Test that only paired devices are returned."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_proxy_object = MagicMock()
        
        mock_devices = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                "org.bluez.Device1": {
                    "Name": "PairedDevice",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Paired": True,
                    "Connected": False,
                    "Trusted": False,
                }
            },
            "/org/bluez/hci0/dev_11_22_33_44_55_66": {
                "org.bluez.Device1": {
                    "Name": "UnpairedDevice",
                    "Address": "11:22:33:44:55:66",
                    "Paired": False,
                    "Connected": False,
                    "Trusted": False,
                }
            }
        }
        
        async def mock_get_managed_objects():
            return mock_devices
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_bus.get_proxy_object.return_value = mock_proxy_object
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            devices = await get_paired_devices()
            
            assert len(devices) == 1
            assert devices[0]["name"] == "PairedDevice"

    @pytest.mark.asyncio
    async def test_get_paired_devices_dbus_error(self):
        """Test get_paired_devices error handling on DBus error."""
        async def mock_connect():
            raise MockDBusError("Connection failed")
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            with pytest.raises(MockDBusError):
                await get_paired_devices()

    @pytest.mark.asyncio
    async def test_get_paired_devices_general_error(self):
        """Test get_paired_devices error handling on general error."""
        async def mock_connect():
            raise RuntimeError("Unexpected error")
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            with pytest.raises(RuntimeError):
                await get_paired_devices()


class TestUnpairDevice:
    """Tests for unpair_device() async function."""

    @pytest.mark.asyncio
    async def test_unpair_device_success(self):
        """Test successful device unpairing."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_adapter_interface = MagicMock()
        mock_proxy_object = MagicMock()
        mock_adapter_proxy = MagicMock()
        
        mock_devices = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                "org.bluez.Device1": {
                    "Name": "TestDevice",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Paired": True,
                }
            }
        }
        
        async def mock_get_managed_objects():
            return mock_devices
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_adapter_interface.call_RemoveDevice = AsyncMock()
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_adapter_proxy.get_interface.return_value = mock_adapter_interface
        
        call_count = 0
        def get_proxy_object_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_proxy_object
            else:
                return mock_adapter_proxy
        
        mock_bus.get_proxy_object.side_effect = get_proxy_object_side_effect
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import unpair_device
            
            result = await unpair_device("AA:BB:CC:DD:EE:FF")
            
            assert result["status"] == "unpaired"
            assert result["address"] == "AA:BB:CC:DD:EE:FF"
            mock_adapter_interface.call_RemoveDevice.assert_called_once()

    @pytest.mark.asyncio
    async def test_unpair_device_uppercase_address(self):
        """Test that device address is normalized to uppercase."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_adapter_interface = MagicMock()
        mock_proxy_object = MagicMock()
        mock_adapter_proxy = MagicMock()
        
        mock_devices = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                "org.bluez.Device1": {
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Paired": True,
                }
            }
        }
        
        async def mock_get_managed_objects():
            return mock_devices
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_remove_device(*args, **kwargs):
            pass
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_adapter_interface.call_RemoveDevice = mock_remove_device
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_adapter_proxy.get_interface.return_value = mock_adapter_interface
        
        call_count = 0
        def get_proxy_object_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_proxy_object
            else:
                return mock_adapter_proxy
        
        mock_bus.get_proxy_object.side_effect = get_proxy_object_side_effect
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import unpair_device
            
            result = await unpair_device("aa:bb:cc:dd:ee:ff")
            
            assert result["address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_unpair_device_not_found(self):
        """Test unpair_device when device is not found."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_proxy_object = MagicMock()
        
        async def mock_get_managed_objects():
            return {}
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_bus.get_proxy_object.return_value = mock_proxy_object
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import unpair_device
            
            with pytest.raises(ValueError, match="Device not found"):
                await unpair_device("AA:BB:CC:DD:EE:FF")

    @pytest.mark.asyncio
    async def test_unpair_device_missing_address(self):
        """Test unpair_device with missing address parameter."""
        with patch("src.bluetooth.MessageBus"):
            from src.bluetooth import unpair_device
            
            with pytest.raises(ValueError, match="Missing 'address'"):
                await unpair_device("")

    @pytest.mark.asyncio
    async def test_unpair_device_dbus_error(self):
        """Test unpair_device error handling on DBus error."""
        async def mock_connect():
            raise MockDBusError("Connection failed")
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import unpair_device
            
            with pytest.raises(MockDBusError):
                await unpair_device("AA:BB:CC:DD:EE:FF")

    @pytest.mark.asyncio
    async def test_unpair_device_general_error(self):
        """Test unpair_device error handling on general error."""
        async def mock_connect():
            raise RuntimeError("Unexpected error")
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import unpair_device
            
            with pytest.raises(RuntimeError):
                await unpair_device("AA:BB:CC:DD:EE:FF")


class TestAsyncIntegration:
    """Tests for async/await integration."""

    @pytest.mark.asyncio
    async def test_get_paired_devices_is_coroutine(self):
        """Test that get_paired_devices returns a coroutine."""
        mock_bus = MagicMock()
        mock_om_interface = MagicMock()
        mock_proxy_object = MagicMock()
        
        async def mock_get_managed_objects():
            return {}
        
        async def mock_introspect(*args, **kwargs):
            return "<node></node>"
        
        async def mock_connect():
            return mock_bus
        
        mock_om_interface.call_GetManagedObjects = mock_get_managed_objects
        mock_proxy_object.get_interface.return_value = mock_om_interface
        mock_bus.get_proxy_object.return_value = mock_proxy_object
        mock_bus.introspect = mock_introspect
        
        mock_message_bus = MagicMock()
        mock_message_bus.connect = mock_connect
        
        with patch("src.bluetooth.MessageBus", return_value=mock_message_bus):
            from src.bluetooth import get_paired_devices
            
            result = get_paired_devices()
            assert asyncio.iscoroutine(result)
            await result

    @pytest.mark.asyncio
    async def test_unpair_device_is_coroutine(self):
        """Test that unpair_device returns a coroutine."""
        from src.bluetooth import unpair_device
        
        result = unpair_device("AA:BB:CC:DD:EE:FF")
        assert asyncio.iscoroutine(result)
        # Don't await - we're just checking it's a coroutine
        result.close()
