"""Saving a player's settings restarts the player when that changes anything.

Players read their settings when they start, so a value that is only stored
does nothing until the next reboot -- which to the user looks like the
setting being ignored (hifiberry/hifiberry-os#672).
"""
import json
import os

import configurator.configdb as configdb_module
from configurator.configdb import ConfigDB
from configurator.handlers.player_registry_handler import PlayerRegistryHandler


class FakeServiceManager:
    def __init__(self, active=True, restart_ok=True):
        self.active = active
        self.restart_ok = restart_ok
        self.restarted = []

    def is_active(self, service_name):
        return self.active

    def restart(self, service_name):
        self.restarted.append(service_name)
        if self.restart_ok:
            return True, f"Service '{service_name}' restarted successfully"
        return False, f"Failed to restart service '{service_name}': boom"


def _setup(tmp_path, service_manager):
    players_d = tmp_path / "players.d"
    os.makedirs(str(players_d), exist_ok=True)
    with open(os.path.join(str(players_d), "shairport.json"), "w") as f:
        json.dump({
            "name": "Airplay",
            "provided_by": "shairport-sync",
            "systemd_service": "shairport",
            "icon": "shairport",
            "settings": [
                {"key": "airplay_version", "type": "select",
                 "label": "AirPlay version", "default": "2",
                 "options": [{"value": "2", "label": "AirPlay 2"},
                             {"value": "1", "label": "AirPlay 1"}]},
                {"key": "token", "type": "secret", "label": "Token", "default": ""},
            ],
        }, f)
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d),
                                    service_manager=service_manager)
    return handler, configdb


def test_changed_setting_restarts_running_player(tmp_path):
    sm = FakeServiceManager(active=True)
    handler, _ = _setup(tmp_path, sm)
    result = handler.save_player_settings("shairport", {"airplay_version": "1"})
    assert result["applied"] == ["airplay_version"]
    assert result["restarted"] is True
    assert sm.restarted == ["shairport"]


def test_unchanged_setting_does_not_restart(tmp_path):
    sm = FakeServiceManager(active=True)
    handler, configdb = _setup(tmp_path, sm)
    configdb.set("player.shairport.airplay_version", "1")
    result = handler.save_player_settings("shairport", {"airplay_version": "1"})
    assert result["applied"] == ["airplay_version"]
    assert result["restarted"] is False
    assert sm.restarted == []


def test_stopped_player_is_not_started(tmp_path):
    sm = FakeServiceManager(active=False)
    handler, _ = _setup(tmp_path, sm)
    result = handler.save_player_settings("shairport", {"airplay_version": "1"})
    assert result["applied"] == ["airplay_version"]
    assert result["restarted"] is False
    assert sm.restarted == []


def test_new_secret_counts_as_change(tmp_path, monkeypatch):
    monkeypatch.setattr(configdb_module, "KEY_FILE", str(tmp_path / "configdb.key"))
    sm = FakeServiceManager(active=True)
    handler, _ = _setup(tmp_path, sm)
    result = handler.save_player_settings("shairport", {"token": "abc"})
    assert result["applied"] == ["token"]
    assert result["restarted"] is True


def test_failed_restart_is_reported_not_raised(tmp_path):
    sm = FakeServiceManager(active=True, restart_ok=False)
    handler, configdb = _setup(tmp_path, sm)
    result = handler.save_player_settings("shairport", {"airplay_version": "1"})
    assert result["applied"] == ["airplay_version"]
    assert result["restarted"] is False
    assert any("restart" in e for e in result["errors"])
    # The value is stored even though the restart failed.
    assert configdb.get("player.shairport.airplay_version") == "1"


def test_without_service_manager_settings_are_still_stored(tmp_path):
    handler, configdb = _setup(tmp_path, None)
    result = handler.save_player_settings("shairport", {"airplay_version": "1"})
    assert result["applied"] == ["airplay_version"]
    assert result["restarted"] is False
    assert configdb.get("player.shairport.airplay_version") == "1"


def test_rejected_value_does_not_restart(tmp_path):
    sm = FakeServiceManager(active=True)
    handler, _ = _setup(tmp_path, sm)
    result = handler.save_player_settings("shairport", {"nope": "1"})
    assert result["applied"] == []
    assert result["restarted"] is False
    assert sm.restarted == []
