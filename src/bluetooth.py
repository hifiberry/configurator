import logging
import sys
import os
import configparser
from pathlib import Path
from typing import Dict, List, Any

from dbus_fast.aio import MessageBus
from dbus_fast import DBusError, BusType

# From the user's script
class ConfigFileManager:
    config_path = "~/.config/hifiberry/bluetooth.conf"
    config_path = Path(config_path).expanduser()

    def __init__(self):
        # Set up logger
        self.logger = logging.getLogger("hbos-bluetooth-service")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.info("Initializing ConfigFileManager...")


        self.config_file = Path(self.config_path)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.config_file.exists():
            self.create_config_file()

        self.load_config_values()

    def create_config_file(self):
        try:
            # Create parent directories if they don't exist
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            # Create the file
            with open(self.config_path, "w") as f:
                f.write("[Bluetooth]\n")
                f.write("capability=NoInputNoOutput\n")
            self.logger.info(f"Created config file: {self.config_path}")

        except Exception as e:
            self.logger.error(f"Error creating config file: {e}")

    def load_config_values(self):
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file)

        self.capability = self.config.get("Bluetooth", "capability", fallback="KeyboardDisplay")

        self.discoverable = self.config.getboolean("Bluetooth", "discoverable", fallback="True")
        self.discoverable_timeout = self.config.getint("Bluetooth", "discoverable_timeout", fallback="0")

        self.pairable = self.config.getboolean("Bluetooth", "pairable", fallback="True")
        self.pairable_timeout = self.config.getint("Bluetooth", "pairable_timeout", fallback="0")

        self.logger.info(f"Bluetooth capability: {self.capability}")
        self.logger.info(f"Discoverable: {self.discoverable}")
        self.logger.info(f"Discoverable timeout: {self.discoverable_timeout}")
        self.logger.info(f"Pairable: {self.pairable}")
        self.logger.info(f"Pairable timeout: {self.pairable_timeout}")

    def set_config_value(self, section: str, key: str, value: str) -> None:
        try:
            if not self.config.has_section(section):
                self.config.add_section(section)

            self.config.set(section, key, value)

            # Save changes to file
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)

            self.logger.info(f"Set {section}.{key} = {value}")

        except Exception as e:
            self.logger.error(f"Error setting config value: {e}")
            self.logger.info(f"capability: {self.capability}")
            self.logger.info(f"discoverable: {self.discoverable}")
            self.logger.info(f"discoverable_timeout: {self.discoverable_timeout}")
            self.logger.info(f"pairable: {self.pairable}")
            self.logger.info(f"pairable_timeout: {self.pairable_timeout}")

# New functions based on the user's Flask routes

def get_bluetooth_settings() -> Dict[str, Any]:
    """Returns bluetooth settings."""
    cfm = ConfigFileManager()
    return {
        "capability": cfm.capability,
        "discoverable": cfm.discoverable,
        "discoverableTimeout": cfm.discoverable_timeout,
        "pairable": cfm.pairable,
        "pairableTimeout": cfm.pairable_timeout,
    }

def set_bluetooth_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Sets bluetooth settings."""
    cfm = ConfigFileManager()
    valid_keys = [
        "capability",
        "discoverable",
        "discoverable_timeout",
        "pairable",
        "pairable_timeout",
    ]
    for key in valid_keys:
        if key in settings:
            value = settings.get(key)
            if key in ["discoverable_timeout", "pairable_timeout"] and value == "":
                value = "0"
            cfm.set_config_value("Bluetooth", key, str(value))
    return get_bluetooth_settings()


async def get_paired_devices() -> List[Dict[str, Any]]:
    """Returns a list of paired bluetooth devices using dbus-fast."""
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await bus.introspect("org.bluez", "/")
        obj = bus.get_proxy_object("org.bluez", "/", introspection)
        
        # Get the ObjectManager interface
        om = obj.get_interface("org.freedesktop.DBus.ObjectManager")  # type: ignore
        objects = await om.call_GetManagedObjects()  # type: ignore
        
        devices: List[Dict[str, Any]] = []
        for path, interfaces in objects.items():  # type: ignore
            if "org.bluez.Device1" in interfaces:  # type: ignore
                device = interfaces["org.bluez.Device1"]  # type: ignore
                if device.get("Paired", False):  # type: ignore
                    devices.append({
                        "name": str(device.get("Name", "Unknown")),  # type: ignore
                        "address": str(device.get("Address")),  # type: ignore
                        "connected": bool(device.get("Connected", False)),  # type: ignore
                        "trusted": bool(device.get("Trusted", False)),  # type: ignore
                    })
        
        return devices
        
    except Exception as e:
        if (
            isinstance(DBusError, type)
            and issubclass(DBusError, BaseException)
            and isinstance(e, DBusError)
        ):
            logging.error(f"DBus error getting paired devices: {e}")
        else:
            logging.error(f"Error getting paired devices: {e}")
        raise


async def unpair_device(address: str) -> Dict[str, str]:
    """Unpairs a bluetooth device using dbus-fast."""
    if not address:
        raise ValueError("Missing 'address' query parameter")

    address = address.upper()
    
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await bus.introspect("org.bluez", "/")
        obj = bus.get_proxy_object("org.bluez", "/", introspection)
        
        # Get the ObjectManager interface
        om = obj.get_interface("org.freedesktop.DBus.ObjectManager")  # type: ignore
        objects = await om.call_GetManagedObjects()  # type: ignore
        
        # Find the device object path and its adapter
        for path, interfaces in objects.items():  # type: ignore
            if "org.bluez.Device1" in interfaces:  # type: ignore
                device = interfaces["org.bluez.Device1"]  # type: ignore
                device_address: str = device.get("Address", "")  # type: ignore
                if device_address.upper() == address:  # type: ignore
                    # Find the adapter this device belongs to
                    adapter_path = "/".join(path.split("/")[:-1])  # type: ignore
                    adapter_introspection = await bus.introspect("org.bluez", adapter_path)
                    adapter_obj = bus.get_proxy_object("org.bluez", adapter_path, adapter_introspection)
                    adapter = adapter_obj.get_interface("org.bluez.Adapter1")  # type: ignore
                    
                    # Remove the device
                    await adapter.call_RemoveDevice(path)  # type: ignore
                    return {"status": "unpaired", "address": address}
        
        raise ValueError("Device not found")
        
    except Exception as e:
        if (
            isinstance(DBusError, type)
            and issubclass(DBusError, BaseException)
            and isinstance(e, DBusError)
        ):
            logging.error(f"DBus error unpairing device: {e}")
        else:
            logging.error(f"Error unpairing device: {e}")
        raise
