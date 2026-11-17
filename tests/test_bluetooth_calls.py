"""The paired-devices list and unpairing never wait on a BlueZ that is not there.

Like get_bluetooth_status(), they must not make D-Bus start BlueZ on a device
without a controller (a 15-25 s activation timeout), and every call to a
running bluetoothd is bounded by DBUS_TIMEOUT.
"""

import pytest

# First: it stubs python3-dbus where it is not installed, before
# configurator.bluetooth imports it.
from tests.test_bluetooth_status import ADAPTER_PATH, DEVICE_PATH, _objects, _patched

from configurator import bluetooth

PAIRED = {"Name": "Phone", "Address": "80:B9:89:1E:B5:6F", "Paired": True, "Connected": False}
UNPAIRED = {"Name": "Other", "Address": "11:22:33:44:55:66", "Paired": False}


def _bus_calls(fake):
    return [c for c in fake.calls if c[0] != "SystemBus"]


def test_paired_devices_without_hardware_asks_nothing():
    with _patched(_objects([], 0, devices=[PAIRED]), hardware=False) as fake:
        assert bluetooth.get_paired_devices() == []
    assert fake.calls == []


def test_paired_devices_without_bluez_never_activates_it():
    with _patched(_objects([], 0, devices=[PAIRED]), has_owner=False) as fake:
        assert bluetooth.get_paired_devices() == []
    assert [c[0] for c in _bus_calls(fake)] == ["name_has_owner"]


def test_paired_devices_are_read_with_a_timeout():
    with _patched(_objects([], 0, devices=[PAIRED, UNPAIRED])) as fake:
        devices = bluetooth.get_paired_devices()
    assert [d["address"] for d in devices] == ["80:B9:89:1E:B5:6F"]
    assert ("GetManagedObjects", {"timeout": bluetooth.DBUS_TIMEOUT}) in fake.calls
    for call in fake.calls:
        if call[0] == "get_object":
            assert call[2] == {"introspect": False}


def test_unpair_without_hardware_is_a_clear_error():
    with _patched(_objects([], 0, devices=[PAIRED]), hardware=False) as fake:
        with pytest.raises(ValueError, match="No Bluetooth hardware"):
            bluetooth.unpair_device("80:B9:89:1E:B5:6F")
    assert fake.calls == []


def test_unpair_without_bluez_never_activates_it():
    with _patched(_objects([], 0, devices=[PAIRED]), has_owner=False) as fake:
        with pytest.raises(ValueError, match="BlueZ is not running"):
            bluetooth.unpair_device("80:B9:89:1E:B5:6F")
    assert [c[0] for c in _bus_calls(fake)] == ["name_has_owner"]


def test_unpair_removes_the_device_with_a_timeout():
    with _patched(_objects([], 0, devices=[PAIRED])) as fake:
        result = bluetooth.unpair_device("80:b9:89:1e:b5:6f")
    assert result == {"status": "unpaired", "address": "80:B9:89:1E:B5:6F"}
    assert ("RemoveDevice", f"{DEVICE_PATH}_0", {"timeout": bluetooth.DBUS_TIMEOUT}) in fake.calls
    assert ("GetManagedObjects", {"timeout": bluetooth.DBUS_TIMEOUT}) in fake.calls
    adapters = [c for c in fake.calls if c[0] == "get_object" and c[1] == ("org.bluez", ADAPTER_PATH)]
    assert adapters and all(c[2] == {"introspect": False} for c in adapters)
