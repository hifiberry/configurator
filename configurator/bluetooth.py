import logging
import sys
import os
import configparser
from pathlib import Path
import dbus

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

    def set_config_value(self, section, key, value):
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

def get_bluetooth_settings():
    """Returns bluetooth settings."""
    cfm = ConfigFileManager()
    return {
        "capability": cfm.capability,
        "discoverable": cfm.discoverable,
        "discoverableTimeout": cfm.discoverable_timeout,
        "pairable": cfm.pairable,
        "pairableTimeout": cfm.pairable_timeout,
    }

def set_bluetooth_settings(settings):
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
            cfm.set_config_value("Bluetooth", key, value)
    return get_bluetooth_settings()


def get_paired_devices():
    """Returns a list of paired bluetooth devices."""
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"),
                             "org.freedesktop.DBus.ObjectManager")
    objects = manager.GetManagedObjects()
    devices = []

    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            if device.get("Paired", False):
                devices.append({
                    "name": str(device.get("Name", "Unknown")),
                    "address": str(device.get("Address")),
                    "connected": bool(device.get("Connected", False)),
                    "trusted": bool(device.get("Trusted", False)),
                })
    return devices

def unpair_device(address):
    """Unpairs a bluetooth device."""
    if not address:
        raise ValueError("Missing 'address' query parameter")

    address = address.upper()
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"),
                             "org.freedesktop.DBus.ObjectManager")
    objects = manager.GetManagedObjects()

    # Find the device object path and its adapter
    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            if device.get("Address", "").upper() == address:
                # Find the adapter this device belongs to
                adapter_path = "/".join(path.split("/")[:-1])
                adapter_obj = dbus.Interface(bus.get_object("org.bluez", adapter_path),
                                             "org.bluez.Adapter1")
                adapter_obj.RemoveDevice(path)
                return {"status": "unpaired", "address": address}

    raise ValueError("Device not found")
