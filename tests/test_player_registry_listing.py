import json
import os
from configurator.handlers.player_registry_handler import PlayerRegistryHandler
from configurator.configdb import ConfigDB


def _write_descriptor(dir_path, filename, descriptor):
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), "w") as f:
        json.dump(descriptor, f)


def test_build_players_includes_settings_with_default_value(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "analog.json", {
        "name": "Analog Input",
        "provided_by": "analog-recognition",
        "systemd_service": "analog-recognition",
        "icon": "analog",
        "settings": [
            {"key": "songrec_enabled", "type": "toggle",
             "label": "Recognize tracks", "default": True},
        ],
    })
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    players = handler._build_players()
    assert len(players) == 1
    settings = players[0]["settings"]
    assert settings[0]["key"] == "songrec_enabled"
    assert settings[0]["value"] is True  # falls back to default when unset


def test_build_players_reads_stored_value(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "analog.json", {
        "name": "Analog Input",
        "provided_by": "analog-recognition",
        "systemd_service": "analog-recognition",
        "icon": "analog",
        "settings": [
            {"key": "songrec_enabled", "type": "toggle",
             "label": "Recognize tracks", "default": True},
        ],
    })
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    configdb.set("player.analog-recognition.songrec_enabled", "false")
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    players = handler._build_players()
    assert players[0]["settings"][0]["value"] is False


def test_build_players_no_settings_key_yields_empty_list(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "lms.json", {
        "name": "LMS", "provided_by": "squeezelite",
        "systemd_service": "squeezelite", "icon": "squeezelite",
    })
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    assert handler._build_players()[0]["settings"] == []
