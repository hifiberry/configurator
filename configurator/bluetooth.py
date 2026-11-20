import logging
import sys
import os
import configparser
import re
from pathlib import Path
import dbus

#: Exists only when the kernel has registered a Bluetooth controller.
BLUETOOTH_SYSFS = "/sys/class/bluetooth"

#: Seconds to wait for BlueZ. A hung bluetoothd must not stall system info.
DBUS_TIMEOUT = 2


class BluetoothUnavailable(Exception):
    """No Bluetooth controller, or BlueZ is not running."""


def _bluez():
    """The system bus with BlueZ on it, without ever starting BlueZ.

    Without a controller bluetooth.service is skipped, so asking the bus for
    org.bluez would make D-Bus try to start BlueZ and wait out its activation
    timeout (15-25 s). Check first, and look objects up without introspection.
    """
    if not os.path.isdir(BLUETOOTH_SYSFS):
        raise BluetoothUnavailable("No Bluetooth hardware")
    bus = dbus.SystemBus()
    if not bus.name_has_owner("org.bluez"):
        raise BluetoothUnavailable("BlueZ is not running")
    return bus


def _managed_objects(bus):
    manager = dbus.Interface(
        bus.get_object("org.bluez", "/", introspect=False),
        "org.freedesktop.DBus.ObjectManager")
    return manager.GetManagedObjects(timeout=DBUS_TIMEOUT)


ADAPTER_IFACE = "org.bluez.Adapter1"
_ADDRESS = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def _configured_adapter():
    """The adapter address set in bluetooth.conf, "" for none.

    Read without ConfigFileManager, which creates the file: asking which
    adapter is chosen must not write anything.
    """
    config = configparser.ConfigParser()
    try:
        config.read(ConfigFileManager.config_path)
    except configparser.Error:
        return ""
    return config.get("Bluetooth", "adapter", fallback="").strip().upper()


def _chosen_adapter(objects, configured):
    """The adapter hifiberry-bluetooth uses, as it chooses it.

    Returns (path, chosen_by_config). The configured address when it is
    present; otherwise the first adapter, with the others left alone.
    """
    adapters = sorted(
        (str(path), str(ifaces[ADAPTER_IFACE].get("Address", "")).upper())
        for path, ifaces in objects.items() if ADAPTER_IFACE in ifaces)
    if not adapters:
        return None, False
    for path, address in adapters:
        if configured and address == configured:
            return path, True
    return adapters[0][0], False


def _adapter_bus(path):
    """"usb" for a USB adapter, "built-in" for one on the board (UART, SDIO)."""
    name = path.rsplit("/", 1)[-1]
    device = os.path.realpath(os.path.join(BLUETOOTH_SYSFS, name, "device"))
    return "usb" if "/usb" in device else "built-in"


def _adapter_list(objects, chosen):
    return [
        {
            "address": str(ifaces[ADAPTER_IFACE].get("Address", "")),
            "name": str(ifaces[ADAPTER_IFACE].get("Alias", "")),
            "bus": _adapter_bus(str(path)),
            "powered": bool(ifaces[ADAPTER_IFACE].get("Powered", False)),
            "selected": str(path) == chosen,
        }
        for path, ifaces in sorted(objects.items()) if ADAPTER_IFACE in ifaces
    ]


def _paired(objects, scope):
    """Paired devices, of the adapter at `scope` only when it is given."""
    devices = []
    for path, interfaces in sorted(objects.items()):
        if "org.bluez.Device1" not in interfaces:
            continue
        if scope and not str(path).startswith(scope + "/"):
            continue
        device = interfaces["org.bluez.Device1"]
        if device.get("Paired", False):
            devices.append({
                "name": str(device.get("Name", "Unknown")),
                "address": str(device.get("Address")),
                "connected": bool(device.get("Connected", False)),
                "trusted": bool(device.get("Trusted", False)),
            })
    return devices

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
        self.adapter = self.config.get("Bluetooth", "adapter", fallback="").strip().upper()

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
    """Returns bluetooth settings, and the adapters to choose from.

    "adapter" is the configured address ("" for the first adapter);
    "adapters" lists every adapter BlueZ has, the one in use marked
    "selected". Without Bluetooth the list is empty.
    """
    cfm = ConfigFileManager()
    try:
        objects = _managed_objects(_bluez())
    except Exception:
        objects = {}
    chosen, _ = _chosen_adapter(objects, cfm.adapter)
    return {
        "capability": cfm.capability,
        "discoverable": cfm.discoverable,
        "discoverableTimeout": cfm.discoverable_timeout,
        "pairable": cfm.pairable,
        "pairableTimeout": cfm.pairable_timeout,
        "adapter": cfm.adapter,
        "adapters": _adapter_list(objects, chosen),
    }

def set_bluetooth_settings(settings):
    """Sets bluetooth settings.

    "adapter" takes an address like AA:BB:CC:DD:EE:FF, or "" for the first
    adapter; anything else is a ValueError.
    """
    cfm = ConfigFileManager()
    valid_keys = [
        "capability",
        "discoverable",
        "discoverable_timeout",
        "pairable",
        "pairable_timeout",
        "adapter",
    ]
    for key in valid_keys:
        if key in settings:
            value = settings.get(key)
            if key in ["discoverable_timeout", "pairable_timeout"] and value == "":
                value = "0"
            if key == "adapter":
                value = (value or "").strip().upper()
                if value and not _ADDRESS.match(value):
                    raise ValueError(f"Not a Bluetooth address: {value!r}")
            cfm.set_config_value("Bluetooth", key, value)
    return get_bluetooth_settings()


def get_paired_devices():
    """Returns a list of paired bluetooth devices; none without Bluetooth.

    With an adapter chosen in bluetooth.conf, only that adapter's devices:
    the others are powered off, and their pairings do not reach this one.
    """
    try:
        objects = _managed_objects(_bluez())
    except BluetoothUnavailable:
        return []
    chosen, by_config = _chosen_adapter(objects, _configured_adapter())
    return _paired(objects, chosen if by_config else None)

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
        objects = _managed_objects(_bluez())
    except BluetoothUnavailable as e:
        status["issues"].append(str(e))
        return status
    except Exception as e:
        # bluez absent (hbos-minimal before 0.14 shipped it), bluetoothd hung,
        # or no system bus. All the same to a reader: no Bluetooth.
        status["issues"].append(f"BlueZ is not reachable: {e}")
        return status

    chosen, by_config = _chosen_adapter(objects, _configured_adapter())
    adapter_props = objects[chosen][ADAPTER_IFACE] if chosen else None

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

    status["devices"] = _paired(objects, chosen if by_config else None)

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
    try:
        bus = _bluez()
    except BluetoothUnavailable as e:
        # The handler answers a ValueError with 400, as for an unknown device.
        raise ValueError(str(e))
    objects = _managed_objects(bus)

    # Find the device object path and its adapter
    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            if device.get("Address", "").upper() == address:
                # Find the adapter this device belongs to
                adapter_path = "/".join(path.split("/")[:-1])
                adapter_obj = dbus.Interface(
                    bus.get_object("org.bluez", adapter_path, introspect=False),
                    "org.bluez.Adapter1")
                adapter_obj.RemoveDevice(path, timeout=DBUS_TIMEOUT)
                return {"status": "unpaired", "address": address}

    raise ValueError("Device not found")
