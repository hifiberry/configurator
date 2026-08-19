import json
import os

import configurator.configdb as configdb_module
from configurator.configdb import ConfigDB
from configurator.handlers.player_registry_handler import PlayerRegistryHandler


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(configdb_module, "KEY_FILE", str(tmp_path / "configdb.key"))
    players_d = tmp_path / "players.d"
    os.makedirs(str(players_d), exist_ok=True)
    with open(os.path.join(str(players_d), "soloist.json"), "w") as f:
        json.dump({
            "name": "Spotify (Soloist)",
            "provided_by": "soloist",
            "systemd_service": "soloist",
            "icon": "soloist",
            "settings": [
                {"key": "api_key", "type": "secret",
                 "label": "Soloist API key", "default": ""},
            ],
        }, f)
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    return handler, configdb


def test_secret_setting_is_stored_encrypted(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    applied, errors = handler.set_player_settings("soloist", {"api_key": "abc123"})
    assert applied == ["api_key"]
    assert errors == []

    # Decryptable with the key...
    assert configdb.get("player.soloist.api_key", secure=True) == "abc123"
    # ...and not present in the clear.
    raw = configdb.get("player.soloist.api_key")
    assert "abc123" not in raw


def test_secret_value_is_never_returned_in_the_listing(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch)
    handler.set_player_settings("soloist", {"api_key": "abc123"})

    players = handler._build_players()
    setting = players[0]["settings"][0]

    assert setting["type"] == "secret"
    assert setting["is_set"] is True
    assert "value" not in setting
    assert "abc123" not in json.dumps(players)


def test_secret_reports_not_set_when_absent(tmp_path, monkeypatch):
    handler, _ = _setup(tmp_path, monkeypatch)
    setting = handler._build_players()[0]["settings"][0]
    assert setting["is_set"] is False
    assert "value" not in setting


def test_empty_secret_clears_the_stored_value(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    handler.set_player_settings("soloist", {"api_key": "abc123"})
    assert configdb.get("player.soloist.api_key") is not None

    applied, errors = handler.set_player_settings("soloist", {"api_key": ""})
    assert applied == ["api_key"]
    assert errors == []
    assert configdb.get("player.soloist.api_key") is None
    assert handler._build_players()[0]["settings"][0]["is_set"] is False


def test_whitespace_only_secret_clears_rather_than_storing_blanks(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    handler.set_player_settings("soloist", {"api_key": "abc123"})

    applied, errors = handler.set_player_settings("soloist", {"api_key": "   "})
    assert applied == ["api_key"]
    assert configdb.get("player.soloist.api_key") is None


def test_secret_is_stripped_before_storing(tmp_path, monkeypatch):
    """Users paste keys; a trailing newline must not become part of the key."""
    handler, configdb = _setup(tmp_path, monkeypatch)
    handler.set_player_settings("soloist", {"api_key": "  abc123\n"})
    assert configdb.get("player.soloist.api_key", secure=True) == "abc123"


def test_non_string_secret_is_rejected(tmp_path, monkeypatch):
    handler, configdb = _setup(tmp_path, monkeypatch)
    applied, errors = handler.set_player_settings("soloist", {"api_key": 12345})
    assert applied == []
    assert any("api_key" in e for e in errors)
    assert configdb.get("player.soloist.api_key") is None


def test_secret_declaration_survives_sanitize(tmp_path, monkeypatch):
    """A secret with the four required fields must not be dropped."""
    from configurator.handlers.player_registry_handler import sanitize_settings
    descriptor = {"settings": [
        {"key": "api_key", "type": "secret", "label": "Key", "default": ""},
    ]}
    assert len(sanitize_settings(descriptor)) == 1
