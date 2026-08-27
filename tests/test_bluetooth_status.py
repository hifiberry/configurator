import sys
import types
from unittest.mock import patch

# configurator.bluetooth imports python3-dbus, which is a hard dependency of
# the package but is not installable into a plain venv (it needs the system
# libdbus headers). Stub it so the pure-logic parts stay testable anywhere.
if "dbus" not in sys.modules:  # pragma: no cover - environment dependent
    _stub = types.ModuleType("dbus")
    _stub.SystemBus = lambda: object()
    _stub.Interface = lambda *a, **k: None
    sys.modules["dbus"] = _stub

from configurator import bluetooth


A2DP_SINK = "0000110b-0000-1000-8000-00805f9b34fb"
A2DP_SOURCE = "0000110a-0000-1000-8000-00805f9b34fb"
AVRCP = "0000110e-0000-1000-8000-00805f9b34fb"

ADAPTER_PATH = "/org/bluez/hci0"
DEVICE_PATH = "/org/bluez/hci0/dev_80_B9_89_1E_B5_6F"


def _objects(uuids, cod, powered=True, devices=()):
    managed = {
        ADAPTER_PATH: {
            "org.bluez.Adapter1": {
                "Alias": "HiFiBerry-tannoy",
                "Address": "DC:A6:32:34:6F:63",
                "Powered": powered,
                "Discoverable": True,
                "DiscoverableTimeout": 60,
                "Pairable": True,
                "Class": cod,
                "UUIDs": list(uuids),
            }
        }
    }
    for i, dev in enumerate(devices):
        managed[f"{DEVICE_PATH}_{i}"] = {"org.bluez.Device1": dev}
    return managed


class _FakeInterface:
    def __init__(self, managed):
        self._managed = managed

    def GetManagedObjects(self):
        return self._managed


class _FakeBus:
    def get_object(self, *args, **kwargs):
        return object()


class _FakeDbus:
    """Stands in for the dbus module, serving a fixed object tree."""

    def __init__(self, managed):
        self._managed = managed

    def SystemBus(self):
        return _FakeBus()

    def Interface(self, *args, **kwargs):
        return _FakeInterface(self._managed)


def _patched(managed):
    """Patch dbus so get_bluetooth_status() sees the given managed objects."""
    return patch.object(bluetooth, "dbus", _FakeDbus(managed))


# --- The verdict --------------------------------------------------------
#
# audio_ready is the field the system-info page leads with. It is not "is
# Bluetooth on" -- an adapter can be powered, discoverable and pairable and
# still be useless as a speaker, which is exactly the state every HiFiBerryOS
# device shipped in before the WirePlumber seat-monitoring fix
# (hifiberry/hifiberry-os#641, #642).


def test_audio_ready_when_a2dp_sink_endpoint_is_registered():
    with _patched(_objects([A2DP_SINK, A2DP_SOURCE, AVRCP], 0x006C0414)):
        status = bluetooth.get_bluetooth_status()
    assert status["available"] is True
    assert status["audio_ready"] is True
    assert status["adapter"]["a2dp_sink_registered"] is True


def test_not_audio_ready_without_a2dp_sink_even_though_adapter_looks_fine():
    # The #641/#642 state: powered, discoverable, pairable, AVRCP registered by
    # audiocontrol -- and no A2DP sink, so phones pair and then drop.
    with _patched(_objects([AVRCP], 0x00400000)):
        status = bluetooth.get_bluetooth_status()
    assert status["available"] is True
    assert status["adapter"]["powered"] is True
    assert status["adapter"]["discoverable"] is True
    assert status["audio_ready"] is False
    assert any("A2DP sink" in issue for issue in status["issues"])


def test_not_audio_ready_when_adapter_is_powered_off():
    with _patched(_objects([A2DP_SINK], 0x006C0414, powered=False)):
        status = bluetooth.get_bluetooth_status()
    assert status["audio_ready"] is False
    assert any("not powered" in issue for issue in status["issues"])


# --- Degrading instead of breaking the page -----------------------------


def test_missing_bluez_reports_unavailable_rather_than_raising():
    # No bluez installed is a normal configuration (hbos-minimal before 0.14),
    # not an error that should take down the whole system-info payload.
    with patch.object(bluetooth.dbus, "SystemBus", side_effect=Exception("no bus")):
        status = bluetooth.get_bluetooth_status()
    assert status["available"] is False
    assert status["audio_ready"] is False
    assert status["adapter"] is None
    assert status["issues"]


def test_no_adapter_reports_unavailable():
    with _patched({}):
        status = bluetooth.get_bluetooth_status()
    assert status["available"] is False
    assert any("No Bluetooth adapter" in issue for issue in status["issues"])


# --- Class of device ----------------------------------------------------
#
# A device left at BlueZ's default reads "Miscellaneous", which is why phones
# draw it with a generic icon rather than a speaker.


def test_decode_device_class_names_a_loudspeaker():
    assert bluetooth.decode_device_class(0x006C0414) == ("Audio/Video", "Loudspeaker")


def test_decode_device_class_flags_the_generic_default():
    major, minor = bluetooth.decode_device_class(0x00400000)
    assert major == "Miscellaneous"
    assert minor is None


def test_generic_device_class_is_reported_as_an_issue():
    with _patched(_objects([A2DP_SINK], 0x00400000)):
        status = bluetooth.get_bluetooth_status()
    assert status["adapter"]["device_class"] == "Miscellaneous"
    assert any("generic icon" in issue for issue in status["issues"])


def test_loudspeaker_class_raises_no_issue():
    with _patched(_objects([A2DP_SINK, A2DP_SOURCE], 0x006C0414)):
        status = bluetooth.get_bluetooth_status()
    assert status["adapter"]["device_class"] == "Audio/Video"
    assert status["adapter"]["device_class_detail"] == "Loudspeaker"
    assert not any("generic icon" in issue for issue in status["issues"])


# --- Paired devices -----------------------------------------------------


def test_only_paired_devices_are_listed_with_their_connection_state():
    devices = [
        {"Name": "HiFiBerry.com", "Address": "80:B9:89:1E:B5:6F",
         "Paired": True, "Connected": True, "Trusted": False},
        {"Name": "Passing phone", "Address": "AA:BB:CC:DD:EE:FF",
         "Paired": False, "Connected": False, "Trusted": False},
    ]
    with _patched(_objects([A2DP_SINK], 0x006C0414, devices=devices)):
        status = bluetooth.get_bluetooth_status()
    assert len(status["devices"]) == 1
    only = status["devices"][0]
    assert only["name"] == "HiFiBerry.com"
    assert only["connected"] is True
    assert only["trusted"] is False
