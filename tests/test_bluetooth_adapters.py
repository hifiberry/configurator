"""Choosing among several Bluetooth adapters, as hifiberry-bluetooth does.

The config server reports which adapter is in use, lists the adapters for
the web interface's selector, and shows only the chosen adapter's devices.
"""

import os
from unittest.mock import patch

import pytest

# First: it stubs python3-dbus where it is not installed.
from tests.test_bluetooth_status import A2DP_SINK, _patched

from configurator import bluetooth

BUILTIN = "/org/bluez/hci0"
STICK = "/org/bluez/hci1"
STICK_ADDR = "AA:BB:CC:DD:EE:FF"


def _adapter(address, alias, powered=True):
    return {"org.bluez.Adapter1": {
        "Alias": alias, "Address": address, "Powered": powered,
        "Discoverable": False, "DiscoverableTimeout": 60, "Pairable": True,
        "Class": 0x006C0414, "UUIDs": [A2DP_SINK]}}


def _device(address, paired=True):
    return {"org.bluez.Device1": {"Name": address, "Address": address,
                                  "Paired": paired, "Connected": False}}


def _two_adapters():
    return {
        BUILTIN: _adapter("00:11:22:33:44:55", "speaker", powered=False),
        STICK: _adapter(STICK_ADDR, "HiFiBerry-speaker"),
        BUILTIN + "/dev_11_11_11_11_11_11": _device("11:11:11:11:11:11"),
        STICK + "/dev_22_22_22_22_22_22": _device("22:22:22:22:22:22"),
    }


@pytest.fixture
def configured():
    with patch.object(bluetooth, "_configured_adapter", return_value=STICK_ADDR):
        yield


def test_the_configured_adapter_is_chosen():
    assert bluetooth._chosen_adapter(_two_adapters(), STICK_ADDR) == (STICK, True)


def test_without_a_choice_the_first_adapter_is_used():
    assert bluetooth._chosen_adapter(_two_adapters(), "") == (BUILTIN, False)


def test_a_missing_configured_adapter_falls_back_to_the_first():
    assert bluetooth._chosen_adapter(_two_adapters(), "00:00:00:00:00:01") == (BUILTIN, False)


def test_status_reports_the_chosen_adapter(configured):
    with _patched(_two_adapters()):
        status = bluetooth.get_bluetooth_status()
    assert status["adapter"]["address"] == STICK_ADDR
    assert [d["address"] for d in status["devices"]] == ["22:22:22:22:22:22"]


def test_paired_devices_are_the_chosen_adapters_only(configured):
    with _patched(_two_adapters()):
        devices = bluetooth.get_paired_devices()
    assert [d["address"] for d in devices] == ["22:22:22:22:22:22"]


def test_without_a_choice_every_adapters_devices_are_listed():
    with patch.object(bluetooth, "_configured_adapter", return_value=""), \
            _patched(_two_adapters()):
        devices = bluetooth.get_paired_devices()
    assert [d["address"] for d in devices] == ["11:11:11:11:11:11", "22:22:22:22:22:22"]


def test_the_adapter_list_names_the_bus_and_the_one_in_use():
    with _patched(_two_adapters()):
        sysfs = bluetooth.BLUETOOTH_SYSFS
        usb = os.path.join(sysfs, "usb1", "1-1")
        os.makedirs(usb)
        os.makedirs(os.path.join(sysfs, "hci1"))
        os.symlink(usb, os.path.join(sysfs, "hci1", "device"))
        adapters = bluetooth._adapter_list(_two_adapters(), STICK)
    assert adapters == [
        {"address": "00:11:22:33:44:55", "name": "speaker", "bus": "built-in",
         "powered": False, "selected": False},
        {"address": STICK_ADDR, "name": "HiFiBerry-speaker", "bus": "usb",
         "powered": True, "selected": True},
    ]


class _Config:
    """ConfigFileManager without a file."""
    def __init__(self):
        self.values = {}
        self.capability = "NoInputNoOutput"
        self.discoverable = False
        self.discoverable_timeout = 60
        self.pairable = True
        self.pairable_timeout = 0
        self.adapter = ""

    def set_config_value(self, section, key, value):
        self.values[key] = value
        if key == "adapter":
            self.adapter = value


@pytest.mark.parametrize("given,stored", [
    (STICK_ADDR.lower(), STICK_ADDR),
    ("", ""),
])
def test_setting_the_adapter(given, stored):
    config = _Config()
    with patch.object(bluetooth, "ConfigFileManager", lambda: config), \
            _patched(_two_adapters()):
        result = bluetooth.set_bluetooth_settings({"adapter": given})
    assert config.values["adapter"] == stored
    assert result["adapter"] == stored
    assert len(result["adapters"]) == 2


@pytest.mark.parametrize("bad", ["hci1", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:FF\nx=1"])
def test_a_bad_adapter_address_is_refused(bad):
    config = _Config()
    with patch.object(bluetooth, "ConfigFileManager", lambda: config):
        with pytest.raises(ValueError):
            bluetooth.set_bluetooth_settings({"adapter": bad})
    assert config.values == {}


def test_settings_without_bluetooth_list_no_adapters():
    config = _Config()
    with patch.object(bluetooth, "ConfigFileManager", lambda: config), \
            _patched({}, hardware=False):
        assert bluetooth.get_bluetooth_settings()["adapters"] == []


def test_the_configured_adapter_is_read_without_creating_the_file(tmp_path):
    path = tmp_path / "bluetooth.conf"
    with patch.object(bluetooth.ConfigFileManager, "config_path", path):
        assert bluetooth._configured_adapter() == ""
        assert not path.exists()
        path.write_text("[Bluetooth]\nadapter = aa:bb:cc:dd:ee:ff\n")
        assert bluetooth._configured_adapter() == STICK_ADDR
