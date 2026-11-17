"""config-server must not wait for the network to be online.

It listens on 127.0.0.1 only and restores nothing that needs the network at
start, so waiting for network-online.target only delayed it, and everything
ordered after it (audiocontrol), by NetworkManager-wait-online: about 9 s
at boot on a Pi 4.
"""

import configparser
from pathlib import Path

UNIT = Path(__file__).resolve().parent.parent / "systemd" / "config-server.service"


def _unit_list(section, key):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(UNIT)
    return parser.get(section, key, fallback="").split()


def test_config_server_does_not_wait_for_the_network():
    for key in ("After", "Wants"):
        assert "network-online.target" not in _unit_list("Unit", key), key
        assert "network.target" not in _unit_list("Unit", key), key


def test_config_server_listens_on_localhost_only():
    assert "127.0.0.1" in _unit_list("Service", "ExecStart")


def test_config_server_still_runs_after_detection():
    assert "config-detect.service" in _unit_list("Unit", "After")
