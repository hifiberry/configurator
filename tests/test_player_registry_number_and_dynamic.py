"""Tests for the `number` setting type and URL-sourced select options.

Both exist so a plugin can expose settings that a static descriptor cannot
express: a bounded numeric value, and a list of choices only the plugin knows
at runtime (e.g. AES67 streams announced on the network).
"""

import json
import os

import pytest

from configurator.handlers.player_registry_handler import (
    PlayerRegistryHandler,
    coerce_setting_value,
    sanitize_settings,
)
from configurator.configdb import ConfigDB


def _write_descriptor(dir_path, filename, descriptor):
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), "w") as f:
        json.dump(descriptor, f)


def _number_setting(**overrides):
    setting = {"key": "latency", "type": "number", "label": "Latency",
               "default": 20, "min": 1, "max": 500, "step": 1}
    setting.update(overrides)
    return setting


def _descriptor(settings):
    return {"name": "AES67", "provided_by": "hifiberry-aes67",
            "systemd_service": "aes67", "icon": "aes67", "settings": settings}


# --- number type ---------------------------------------------------------

def test_number_setting_survives_sanitising():
    got = sanitize_settings(_descriptor([_number_setting()]))
    assert len(got) == 1
    assert got[0]["min"] == 1 and got[0]["max"] == 500 and got[0]["step"] == 1


def test_number_setting_without_bounds_is_dropped():
    """Unbounded numbers would let the UI submit anything."""
    assert sanitize_settings(_descriptor([_number_setting(min=None)])) == []


def test_number_setting_with_non_numeric_bounds_is_dropped():
    assert sanitize_settings(_descriptor([_number_setting(max="lots")])) == []


def test_number_setting_with_min_above_max_is_dropped():
    assert sanitize_settings(_descriptor([_number_setting(min=10, max=5)])) == []


def test_step_defaults_to_one_when_absent():
    setting = _number_setting()
    del setting["step"]
    assert sanitize_settings(_descriptor([setting]))[0]["step"] == 1


def test_coerce_number_parses_stored_text():
    assert coerce_setting_value("number", "20") == 20


def test_coerce_number_keeps_fractional_values():
    assert coerce_setting_value("number", "2.5") == 2.5


def test_coerce_number_returns_none_for_nonsense():
    assert coerce_setting_value("number", "soon") is None


def test_stored_number_is_returned_as_number(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_number_setting()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    configdb.set("player.aes67.latency", "10")
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    assert handler._build_players()[0]["settings"][0]["value"] == 10


def test_number_out_of_range_is_rejected(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_number_setting()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    applied, errors = handler.set_player_settings("aes67", {"latency": 9999})
    assert applied == []
    assert errors and "range" in errors[0].lower()
    assert configdb.get("player.aes67.latency", default=None) is None


def test_number_in_range_is_stored(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_number_setting()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    applied, errors = handler.set_player_settings("aes67", {"latency": 10})
    assert applied == ["latency"] and errors == []
    assert configdb.get("player.aes67.latency", default=None) == "10"


def test_non_numeric_submission_is_rejected(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_number_setting()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))

    applied, errors = handler.set_player_settings("aes67", {"latency": "fast"})
    assert applied == [] and errors


# --- URL-sourced select options -----------------------------------------

def _dynamic_select(**overrides):
    setting = {"key": "stream", "type": "select", "label": "Stream", "default": "",
               "options_url": "http://localhost:1083/api/v1/streams",
               "options_path": "streams", "options_value": "name",
               "options_label": "name"}
    setting.update(overrides)
    return setting


def test_select_with_options_url_survives_without_static_options():
    got = sanitize_settings(_descriptor([_dynamic_select()]))
    assert len(got) == 1


def test_select_without_options_or_url_is_still_dropped():
    assert sanitize_settings(_descriptor([
        {"key": "x", "type": "select", "label": "X", "default": ""}])) == []


def test_remote_url_is_refused():
    """config-server runs as root; fetching arbitrary hosts would be an SSRF."""
    assert sanitize_settings(_descriptor([
        _dynamic_select(options_url="http://example.com/streams")])) == []


def test_options_are_fetched_and_mapped(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_dynamic_select()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    handler._fetch_json = lambda url: {"streams": [{"name": "AU-U22 : 1"},
                                                   {"name": "X32 : 2"}]}

    options = handler._build_players()[0]["settings"][0]["options"]
    assert options == [{"value": "AU-U22 : 1", "label": "AU-U22 : 1"},
                       {"value": "X32 : 2", "label": "X32 : 2"}]


def test_unreachable_source_keeps_the_stored_value_as_an_option(tmp_path):
    """Losing the plugin must not silently blank the user's current choice."""
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_dynamic_select()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    configdb.set("player.aes67.stream", "AU-U22 : 1")
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    handler._fetch_json = lambda url: None

    setting = handler._build_players()[0]["settings"][0]
    assert setting["value"] == "AU-U22 : 1"
    assert setting["options"] == [{"value": "AU-U22 : 1", "label": "AU-U22 : 1"}]


def test_unreachable_source_with_no_stored_value_yields_no_options(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_dynamic_select()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    handler._fetch_json = lambda url: None

    assert handler._build_players()[0]["settings"][0]["options"] == []


def test_dynamic_select_accepts_a_fetched_value(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json", _descriptor([_dynamic_select()]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    handler._fetch_json = lambda url: {"streams": [{"name": "AU-U22 : 1"}]}

    applied, errors = handler.set_player_settings("aes67", {"stream": "AU-U22 : 1"})
    assert applied == ["stream"] and errors == []


def test_presentation_hints_are_passed_through():
    """A `widget` hint lets the UI pick a control without new validation here."""
    got = sanitize_settings(_descriptor([_number_setting(widget="slider")]))
    assert got[0]["widget"] == "slider"


def test_presentation_hints_survive_to_the_listing(tmp_path):
    players_d = tmp_path / "players.d"
    _write_descriptor(str(players_d), "aes67.json",
                      _descriptor([_number_setting(widget="slider")]))
    configdb = ConfigDB(db_path=str(tmp_path / "config.sqlite"))
    handler = PlayerRegistryHandler(configdb=configdb, players_d_dir=str(players_d))
    assert handler._build_players()[0]["settings"][0]["widget"] == "slider"
