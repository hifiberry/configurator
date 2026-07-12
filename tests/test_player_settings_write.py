import json
import os
from pathlib import Path
from typing import Any
from src.handlers.player_registry_handler import PlayerRegistryHandler
from src.configdb import ConfigDB


def _setup(tmp_path: Path) -> tuple[Any, ConfigDB]:
    players_d = tmp_path / "players.d"
    os.makedirs(str(players_d), exist_ok=True)
    with open(os.path.join(str(players_d), "analog.json"), "w") as f:
        json.dump({
            "name": "Analog Input",
            "provided_by": "analog-recognition",
            "systemd_service": "analog-recognition",
            "icon": "analog",
            "settings": [
                {"key": "songrec_enabled", "type": "toggle",
                 "label": "Recognize tracks", "default": True},
            ],
        }, f)
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    return handler, configdb


def test_set_player_settings_writes_namespaced_key(tmp_path: Path) -> None:
    handler, configdb = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", {"songrec_enabled": False})
    assert applied == ["songrec_enabled"]
    assert errors == []
    assert configdb.get("player.analog-recognition.songrec_enabled") == "false"


def test_set_player_settings_rejects_unknown_key(tmp_path: Path) -> None:
    handler, _ = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", {"nope": True})
    assert applied == []
    assert any("nope" in e for e in errors)


def test_set_player_settings_unknown_service(tmp_path: Path) -> None:
    handler, _ = _setup(tmp_path)
    applied, errors = handler.set_player_settings("does-not-exist", {"x": 1})
    assert applied == []
    assert errors


def test_set_player_settings_non_dict_body_does_not_crash(tmp_path: Path) -> None:
    """Non-dict body (list, string, number) should return error without crashing."""
    handler, _ = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", ["not", "a", "dict"])
    assert applied == []
    assert errors  # Should have at least one error
    assert not any("Traceback" in e for e in errors)  # No exception message


def test_set_player_settings_coerces_toggle_string_false(tmp_path: Path) -> None:
    """String 'false' for toggle setting should be coerced and stored as 'false'."""
    handler, configdb = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", {"songrec_enabled": "false"})
    assert applied == ["songrec_enabled"]
    assert errors == []
    # The string "false" should be coerced to bool False, then serialized back to "false"
    assert configdb.get("player.analog-recognition.songrec_enabled") == "false"
