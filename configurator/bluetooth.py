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

# A2DP Audio Sink. BlueZ adds this UUID to the adapter's record only once a
# media endpoint for it has been registered -- which on our systems means
# PipeWire's bluez5 monitor is running. Its absence is what made phones see the
# device as something other than a speaker, pair, and then drop the link a few
# seconds later with nothing to stream to. See hifiberry/hifiberry-os#641, #642.
A2DP_SINK_UUID = "0000110b-0000-1000-8000-00805f9b34fb"
A2DP_SOURCE_UUID = "0000110a-0000-1000-8000-00805f9b34fb"

# Class of Device major device classes (bits 12-8), Bluetooth assigned numbers.
_MAJOR_DEVICE_CLASS = {
    0x00: "Miscellaneous",
    0x01: "Computer",
    0x02: "Phone",
    0x03: "Network access point",
    0x04: "Audio/Video",
    0x05: "Peripheral",
    0x06: "Imaging",
    0x07: "Wearable",
    0x08: "Toy",
    0x09: "Health",
    0x1F: "Uncategorized",
}

# Minor device classes (bits 7-2) worth naming, for major class Audio/Video.
_AV_MINOR_DEVICE_CLASS = {
    0x01: "Wearable headset",
    0x02: "Hands-free",
    0x04: "Microphone",
    0x05: "Loudspeaker",
    0x06: "Headphones",
    0x07: "Portable audio",
    0x08: "Car audio",
    0x0A: "HiFi audio device",
}


def decode_device_class(cod):
    """Decode a Class of Device integer into its major/minor device class names.

    Returns (major_name, minor_name). minor_name is None when the major class
    has no name we track. A speaker should read "Audio/Video"/"Loudspeaker";
    a device left at BlueZ's default reads "Miscellaneous", which is why phones
    draw it with a generic icon instead of a speaker.
    """
    major = (cod >> 8) & 0x1F
    minor = (cod >> 2) & 0x3F
    major_name = _MAJOR_DEVICE_CLASS.get(major, f"Unknown (0x{major:02x})")
    minor_name = None
    if major == 0x04:
        minor_name = _AV_MINOR_DEVICE_CLASS.get(minor)
    return major_name, minor_name


def get_bluetooth_status():
    """Report whether Bluetooth audio is actually usable, and why not if it isn't.

    Everything here comes from org.bluez over the system bus. The single most
    useful field is audio_ready: an adapter can be powered, discoverable and
    pairable and still be useless as a speaker if no A2DP sink endpoint was
    ever registered, which is exactly the state every HiFiBerryOS device was in
    before the WirePlumber seat-monitoring fix.

    Never raises: a system without bluez installed, or with bluetoothd stopped,
    reports available=False rather than breaking the whole system-info page.
    """
    status = {
        "available": False,
        "audio_ready": False,
        "adapter": None,
        "devices": [],
        "issues": [],
    }

    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object("org.bluez", "/"),
                                 "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
    except Exception as e:
        # bluez absent (hbos-minimal before 0.14 shipped it), bluetoothd not
        # running, or no system bus. All the same to a reader: no Bluetooth.
        status["issues"].append(f"BlueZ is not reachable: {e}")
        return status

    adapter_props = None
    for path, interfaces in objects.items():
        if "org.bluez.Adapter1" in interfaces:
            adapter_props = interfaces["org.bluez.Adapter1"]
            break

    if adapter_props is None:
        status["issues"].append("No Bluetooth adapter found")
        return status

    status["available"] = True

    uuids = [str(u).lower() for u in adapter_props.get("UUIDs", [])]
    cod = int(adapter_props.get("Class", 0))
    major_name, minor_name = decode_device_class(cod)
    a2dp_sink = A2DP_SINK_UUID in uuids

    status["adapter"] = {
        "alias": str(adapter_props.get("Alias", "")),
        "address": str(adapter_props.get("Address", "")),
        "powered": bool(adapter_props.get("Powered", False)),
        # Configured intent, as BlueZ reports it. Note this is not proof the
        # controller is answering inquiries -- a radio fault can leave this
        # true while the device is undiscoverable.
        "discoverable": bool(adapter_props.get("Discoverable", False)),
        "discoverable_timeout": int(adapter_props.get("DiscoverableTimeout", 0)),
        "pairable": bool(adapter_props.get("Pairable", False)),
        "class": f"0x{cod:06x}",
        "device_class": major_name,
        "device_class_detail": minor_name,
        "a2dp_sink_registered": a2dp_sink,
        "a2dp_source_registered": A2DP_SOURCE_UUID in uuids,
    }

    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            if device.get("Paired", False):
                status["devices"].append({
                    "name": str(device.get("Name", "Unknown")),
                    "address": str(device.get("Address")),
                    "connected": bool(device.get("Connected", False)),
                    "trusted": bool(device.get("Trusted", False)),
                })

    if not status["adapter"]["powered"]:
        status["issues"].append("Adapter is not powered on")
    if not a2dp_sink:
        status["issues"].append(
            "No A2DP sink endpoint is registered, so this device cannot act as "
            "a Bluetooth speaker. Phones may pair but will disconnect shortly "
            "after connecting."
        )
    if major_name != "Audio/Video":
        status["issues"].append(
            f"Class of device is \"{major_name}\" rather than Audio/Video, so "
            "phones will show this device with a generic icon instead of a speaker."
        )

    status["audio_ready"] = status["adapter"]["powered"] and a2dp_sink
    return status


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
