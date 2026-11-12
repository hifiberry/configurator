import json
import os

import configurator.configdb as configdb_module
from configurator.configdb import ConfigDB
from configurator.handlers.player_registry_handler import PlayerRegistryHandler


def _setup(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr(configdb_module, "KEY_FILE", str(tmp_path / "configdb.key"))
    players_d = tmp_path / "players.d"
    os.makedirs(str(players_d), exist_ok=True)
    setting = {"key": "server_url", "type": "text", "label": "Server address",
               "default": "", "pattern": "^(https?://.+)?$"}
    setting.update(overrides)
    with open(os.path.join(str(players_d), "jellyfin.json"), "w") as f:
        json.dump({
            "name": "Jellyfin",
            "provided_by": "jellyfin",
            "systemd_service": "jellyfin",
            "icon": "jellyfin",
            "settings": [setting],
        }, f)
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    return handler, configdb


def test_text_value_is_stored_trimmed_and_listed(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    assert handler.set_player_settings(
        "jellyfin", {"server_url": "  http://192.0.2.5:8096 "}) == (["server_url"], [])
    assert configdb.get("player.jellyfin.server_url") == "http://192.0.2.5:8096"
    assert handler._build_players()[0]["settings"][0]["value"] == "http://192.0.2.5:8096"


def test_text_rejects_pattern_mismatch(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    applied, errors = handler.set_player_settings("jellyfin", {"server_url": "ftp://x"})
    assert applied == [] and errors == ["server_url: invalid format"]
    assert configdb.get("player.jellyfin.server_url", default=None) is None


def test_text_rejects_too_long(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch)
    applied, errors = handler.set_player_settings(
        "jellyfin", {"server_url": "http://" + "a" * 250})
    assert applied == [] and errors == ["server_url: too long (max 256)"]


def test_text_rejects_non_string(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch)
    applied, errors = handler.set_player_settings("jellyfin", {"server_url": 42})
    assert applied == [] and errors == ["server_url: must be a string"]


def test_text_entry_with_invalid_pattern_is_dropped(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch, pattern="(")
    assert handler._build_players()[0]["settings"] == []


def test_text_entry_with_invalid_max_length_is_dropped(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch, max_length=0)
    assert handler._build_players()[0]["settings"] == []


def test_text_custom_max_length_is_enforced(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch, max_length=10, pattern=".*")
    applied, errors = handler.set_player_settings("jellyfin", {"server_url": "a" * 11})
    assert applied == [] and errors == ["server_url: too long (max 10)"]
    assert handler.set_player_settings("jellyfin", {"server_url": "a" * 10}) == (["server_url"], [])


def test_text_of_exactly_default_max_length_is_accepted(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch, pattern=".*")
    assert handler.set_player_settings("jellyfin", {"server_url": "a" * 256}) == (["server_url"], [])
    assert configdb.get("player.jellyfin.server_url") == "a" * 256
