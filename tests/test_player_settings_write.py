import json
import os
from configurator.handlers.player_registry_handler import PlayerRegistryHandler
from configurator.configdb import ConfigDB


def _setup(tmp_path):
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


def test_set_player_settings_writes_namespaced_key(tmp_path):
    handler, configdb = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", {"songrec_enabled": False})
    assert applied == ["songrec_enabled"]
    assert errors == []
    assert configdb.get("player.analog-recognition.songrec_enabled") == "false"


def test_set_player_settings_rejects_unknown_key(tmp_path):
    handler, _ = _setup(tmp_path)
    applied, errors = handler.set_player_settings("analog-recognition", {"nope": True})
    assert applied == []
    assert any("nope" in e for e in errors)


def test_set_player_settings_unknown_service(tmp_path):
    handler, _ = _setup(tmp_path)
    applied, errors = handler.set_player_settings("does-not-exist", {"x": 1})
    assert applied == []
    assert errors
