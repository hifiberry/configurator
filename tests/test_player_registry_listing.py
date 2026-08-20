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


def test_build_players_exposes_conflicts_with(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "soloist.json", {
        "name": "Spotify (Soloist)",
        "provided_by": "soloist-wrapper",
        "systemd_service": "soloist",
        "icon": "soloist",
        "conflicts_with": ["librespot"],
    })
    handler = PlayerRegistryHandler(
        configdb=ConfigDB(db_path=str(tmp_path / "config.sqlite")),
        players_d_dir=str(players_d))

    assert handler._build_players()[0]["conflicts_with"] == ["librespot"]


def test_build_players_defaults_conflicts_to_empty(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "analog.json", {
        "name": "Analog Input",
        "provided_by": "analog-recognition",
        "systemd_service": "analog-recognition",
        "icon": "analog",
    })
    handler = PlayerRegistryHandler(
        configdb=ConfigDB(db_path=str(tmp_path / "config.sqlite")),
        players_d_dir=str(players_d))

    assert handler._build_players()[0]["conflicts_with"] == []


def test_malformed_conflicts_with_does_not_break_the_listing(tmp_path):
    """Every player on the device comes through this one endpoint, so a bad
    value in one descriptor must not take the others down with it."""
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "bad.json", {
        "name": "Broken", "provided_by": "b", "systemd_service": "b",
        "icon": "b", "conflicts_with": {"not": "a list"},
    })
    _write_descriptor(str(players_d), "good.json", {
        "name": "Fine", "provided_by": "g", "systemd_service": "g",
        "icon": "g", "conflicts_with": "librespot",  # bare string is accepted
    })
    handler = PlayerRegistryHandler(
        configdb=ConfigDB(db_path=str(tmp_path / "config.sqlite")),
        players_d_dir=str(players_d))

    players = {p["name"]: p for p in handler._build_players()}
    assert players["Broken"]["conflicts_with"] == []
    assert players["Fine"]["conflicts_with"] == ["librespot"]


def _handler(tmp_path, players_d):
    return PlayerRegistryHandler(
        configdb=ConfigDB(db_path=str(tmp_path / "config.sqlite")),
        players_d_dir=str(players_d))


def test_setup_block_is_exposed(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "soloist.json", {
        "name": "Spotify (Soloist)", "provided_by": "soloist-wrapper",
        "systemd_service": "soloist", "icon": "soloist",
        "setup": {"base_url": "/api/soloist"},
    })
    assert _handler(tmp_path, players_d)._build_players()[0]["setup"] == {
        "base_url": "/api/soloist"}


def test_setup_defaults_to_none(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "mpd.json", {
        "name": "MPD", "provided_by": "mpd", "systemd_service": "mpd", "icon": "mpd"})
    assert _handler(tmp_path, players_d)._build_players()[0]["setup"] is None


def test_setup_trailing_slash_is_normalised(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "x.json", {
        "name": "X", "provided_by": "x", "systemd_service": "x", "icon": "x",
        "setup": {"base_url": "/api/x/"}})
    assert _handler(tmp_path, players_d)._build_players()[0]["setup"]["base_url"] == "/api/x"


def test_setup_rejects_a_non_local_base_url(tmp_path):
    """A descriptor is trusted, but pointing a browser that holds the user's
    session at another origin must not be one typo away."""
    players_d = tmp_path / "players.d"
    for i, bad in enumerate(["https://evil.example/api", "//evil.example/api",
                             "api/x", "", 42, {"nested": True}]):
        _write_descriptor(str(players_d), f"bad{i}.json", {
            "name": f"Bad{i}", "provided_by": "b", "systemd_service": f"b{i}",
            "icon": "b", "setup": {"base_url": bad}})
    players = _handler(tmp_path, players_d)._build_players()
    assert players, "descriptors must still load"
    assert all(p["setup"] is None for p in players)


def test_malformed_setup_does_not_break_the_listing(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "bad.json", {
        "name": "Bad", "provided_by": "b", "systemd_service": "b", "icon": "b",
        "setup": "not-an-object"})
    _write_descriptor(str(players_d), "good.json", {
        "name": "Good", "provided_by": "g", "systemd_service": "g", "icon": "g",
        "setup": {"base_url": "/api/g"}})
    players = {p["name"]: p for p in _handler(tmp_path, players_d)._build_players()}
    assert players["Bad"]["setup"] is None
    assert players["Good"]["setup"] == {"base_url": "/api/g"}
