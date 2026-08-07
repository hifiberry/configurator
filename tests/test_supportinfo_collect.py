# tests/test_supportinfo_collect.py
from unittest.mock import patch

from configurator import supportinfo


FLAT_INFO = {
    "Pi Model": "Raspberry Pi 5 Model B Rev 1.0 5",
    "Memory": "8 GB (8192 MB)",
    "HAT": "HiFiBerry DAC2 HD",
    "Sound Card": "DAC2 HD",
    "UUID": "deadbeef-0000-1111-2222-333344445555",
    "Hostname": "daniels-wohnzimmer",
    "Pretty Hostname": "Daniel's Living Room",
}


def test_collect_system_keeps_hardware_fields():
    with patch.object(supportinfo, "_flat_system_info", return_value=dict(FLAT_INFO)):
        result = supportinfo.collect_system()
    assert result["Pi Model"] == "Raspberry Pi 5 Model B Rev 1.0 5"
    assert result["HAT"] == "HiFiBerry DAC2 HD"
    assert result["Sound Card"] == "DAC2 HD"
    assert result["Memory"] == "8 GB (8192 MB)"


def test_collect_system_drops_identifying_fields():
    with patch.object(supportinfo, "_flat_system_info", return_value=dict(FLAT_INFO)):
        result = supportinfo.collect_system()
    assert "UUID" not in result
    assert "Hostname" not in result
    assert "Pretty Hostname" not in result


def test_collect_system_survives_a_broken_systeminfo():
    with patch.object(supportinfo, "_flat_system_info", side_effect=RuntimeError("boom")):
        result = supportinfo.collect_system()
    assert result == {"error": "could not read system info: boom"}


def test_collect_os_reads_pretty_name():
    os_release = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\n'
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value = os_release.splitlines(True)
        with patch("platform.release", return_value="6.12.0-rpi"), \
             patch("platform.machine", return_value="aarch64"):
            result = supportinfo.collect_os()
    assert result["OS"] == "Debian GNU/Linux 13 (trixie)"
    assert result["Kernel"] == "6.12.0-rpi"
    assert result["Architecture"] == "aarch64"
