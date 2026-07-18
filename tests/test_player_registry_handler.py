#!/usr/bin/env python3
"""
Regression tests for Player Registry handler.

Tests external player discovery from descriptors, icon serving,
and player settings management.
"""

# pylint: disable=import-error,too-many-public-methods
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock Flask response class
class MockResponse:  # pylint: disable=too-few-public-methods
    """Mock Flask Response object"""

    def __init__(self, json_data=None, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.headers = {}

    def get_json(self):
        """Return the mocked JSON payload."""
        return self.json_data


def mock_jsonify(data):
    """Mock Flask jsonify function"""
    return MockResponse(data, 200)


def mock_make_response(data):
    """Mock Flask make_response function"""
    return MockResponse(data, 200)


# Patch Flask imports before importing the handler
def setup_flask_mocks():
    """Setup Flask mocks before importing handler."""
    sys.modules['flask'] = MagicMock()
    sys.modules['flask'].jsonify = mock_jsonify
    sys.modules['flask'].make_response = mock_make_response
    sys.modules['flask'].request = MagicMock()


setup_flask_mocks()

# pylint: disable=wrong-import-position
from handlers.player_registry_handler import (  # noqa: E402
    PlayerRegistryHandler,
    sanitize_settings,
    coerce_setting_value,
    serialize_setting_value,
    setting_value_key,
)


class TestSanitizeSettings(unittest.TestCase):
    """Test setting sanitization and validation."""

    def test_sanitize_empty_settings(self):
        """Return empty list when settings field is missing."""
        descriptor = {"name": "test"}
        result = sanitize_settings(descriptor)
        self.assertEqual(result, [])

    def test_sanitize_non_list_settings(self):
        """Return empty list when settings is not a list."""
        descriptor = {"settings": "not a list"}
        result = sanitize_settings(descriptor)
        self.assertEqual(result, [])

    def test_sanitize_non_dict_entry(self):
        """Skip non-dict entries in settings list."""
        descriptor = {
            "settings": [
                "string entry",
                123,
                {
                    "key": "vol",
                    "type": "select",
                    "label": "Volume",
                    "default": "50",
                    "options": ["50"],
                },
            ]
        }
        result = sanitize_settings(descriptor)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "vol")

    def test_sanitize_missing_required_fields(self):
        """Skip entries missing required fields."""
        descriptor = {"settings": [{"key": "vol"}]}
        result = sanitize_settings(descriptor)
        self.assertEqual(result, [])

    def test_sanitize_invalid_type(self):
        """Skip entries with invalid type."""
        descriptor = {
            "settings": [
                {"key": "vol", "type": "invalid", "label": "Volume", "default": "50"}
            ]
        }
        result = sanitize_settings(descriptor)
        self.assertEqual(result, [])

    def test_sanitize_select_without_options(self):
        """Skip select type without options list."""
        descriptor = {
            "settings": [
                {
                    "key": "player",
                    "type": "select",
                    "label": "Player",
                    "default": "a",
                }
            ]
        }
        result = sanitize_settings(descriptor)
        self.assertEqual(result, [])

    def test_sanitize_valid_toggle(self):
        """Accept valid toggle setting."""
        descriptor = {
            "settings": [
                {
                    "key": "enabled",
                    "type": "toggle",
                    "label": "Enable",
                    "default": True,
                }
            ]
        }
        result = sanitize_settings(descriptor)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "enabled")

    def test_sanitize_valid_select(self):
        """Accept valid select setting with options."""
        descriptor = {
            "settings": [
                {
                    "key": "mode",
                    "type": "select",
                    "label": "Mode",
                    "default": "high",
                    "options": ["low", "high"],
                }
            ]
        }
        result = sanitize_settings(descriptor)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "mode")


class TestCoerceSetting(unittest.TestCase):
    """Test setting value coercion."""

    def test_coerce_none_value(self):
        """Return None for None input."""
        result = coerce_setting_value("toggle", None)
        self.assertIsNone(result)

    def test_coerce_toggle_bool_true(self):
        """Coerce bool True to True."""
        result = coerce_setting_value("toggle", True)
        self.assertTrue(result)

    def test_coerce_toggle_bool_false(self):
        """Coerce bool False to False."""
        result = coerce_setting_value("toggle", False)
        self.assertFalse(result)

    def test_coerce_toggle_string_true(self):
        """Coerce string 'true' to True."""
        for val in ["true", "True", "TRUE", "1", "yes", "on"]:
            result = coerce_setting_value("toggle", val)
            self.assertTrue(result, f"Failed for {val}")

    def test_coerce_toggle_string_false(self):
        """Coerce string 'false' to False."""
        for val in ["false", "False", "0", "no", "off"]:
            result = coerce_setting_value("toggle", val)
            self.assertFalse(result, f"Failed for {val}")

    def test_coerce_select_string(self):
        """Coerce select value to string."""
        result = coerce_setting_value("select", "high")
        self.assertEqual(result, "high")

    def test_coerce_select_number(self):
        """Coerce select number value to string."""
        result = coerce_setting_value("select", 42)
        self.assertEqual(result, "42")


class TestSerializeSetting(unittest.TestCase):
    """Test setting value serialization."""

    def test_serialize_toggle_true(self):
        """Serialize bool True to 'true'."""
        result = serialize_setting_value("toggle", True)
        self.assertEqual(result, "true")

    def test_serialize_toggle_false(self):
        """Serialize bool False to 'false'."""
        result = serialize_setting_value("toggle", False)
        self.assertEqual(result, "false")

    def test_serialize_select_string(self):
        """Serialize select string value."""
        result = serialize_setting_value("select", "high")
        self.assertEqual(result, "high")

    def test_serialize_select_number(self):
        """Serialize select numeric value."""
        result = serialize_setting_value("select", 42)
        self.assertEqual(result, "42")


class TestSettingValueKey(unittest.TestCase):
    """Test ConfigDB key generation for settings."""

    def test_setting_value_key(self):
        """Generate correct ConfigDB key."""
        result = setting_value_key("squeezelite", "volume")
        self.assertEqual(result, "player.squeezelite.volume")


class TestPlayerRegistryHandler(unittest.TestCase):
    """Test PlayerRegistryHandler main functionality."""

    def setUp(self):
        """Create handler with mocked configdb."""
        self.configdb_mock = Mock()
        self.handler = PlayerRegistryHandler(
            configdb=self.configdb_mock, players_d_dir=tempfile.mkdtemp()
        )

    def tearDown(self):
        """Clean up temp directory."""
        if os.path.exists(self.handler.players_d_dir):
            shutil.rmtree(self.handler.players_d_dir)

    def test_load_descriptors_empty_dir(self):
        """Return empty list when players.d directory is empty."""
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(result, [])

    def test_load_descriptors_no_json_files(self):
        """Ignore non-JSON files."""
        # Create a non-JSON file
        non_json = os.path.join(self.handler.players_d_dir, "readme.txt")
        with open(non_json, "w", encoding="utf-8") as f:
            f.write("test")
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(result, [])

    def test_load_descriptors_invalid_json(self):
        """Skip files with invalid JSON."""
        json_file = os.path.join(self.handler.players_d_dir, "bad.json")
        with open(json_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(result, [])

    def test_load_descriptors_not_dict(self):
        """Skip JSON that is not an object."""
        json_file = os.path.join(self.handler.players_d_dir, "array.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(result, [])

    def test_load_descriptors_missing_fields(self):
        """Skip descriptors missing required fields."""
        json_file = os.path.join(self.handler.players_d_dir, "incomplete.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({"name": "test"}, f)
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(result, [])

    def test_load_descriptors_valid(self):
        """Load valid descriptor files."""
        json_file = os.path.join(self.handler.players_d_dir, "squeezelite.json")
        descriptor = {
            "name": "Squeezelite",
            "provided_by": "hifiberry",
            "systemd_service": "squeezelite",
            "icon": "squeezelite",
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(descriptor, f)
        result = self.handler._load_descriptors()  # pylint: disable=protected-access
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Squeezelite")

    def test_list_players_empty(self):
        """Return empty players list when no descriptors."""
        response = self.handler.handle_list_players()
        self.assertEqual(response.json_data["status"], "success")
        self.assertEqual(response.json_data["data"]["players"], [])

    def test_build_players_single(self):
        """Build player entry from valid descriptor."""
        json_file = os.path.join(self.handler.players_d_dir, "squeezelite.json")
        descriptor = {
            "name": "Squeezelite",
            "provided_by": "hifiberry",
            "systemd_service": "squeezelite",
            "icon": "squeezelite",
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(descriptor, f)
        result = self.handler._build_players()  # pylint: disable=protected-access
        self.assertEqual(len(result), 1)
        player = result[0]
        self.assertEqual(player["name"], "Squeezelite")
        self.assertEqual(player["systemd_service"], "squeezelite")
        self.assertIn("icon_url", player)

    def test_player_icon_invalid_name(self):
        """Reject icon with invalid name characters."""
        response = self.handler.handle_player_icon("../etc/passwd")
        self.assertEqual(response[1], 400)
        self.assertEqual(response[0].json_data["status"], "error")

    def test_player_icon_not_found(self):
        """Return 404 when icon file doesn't exist."""
        response = self.handler.handle_player_icon("nonexistent")
        self.assertEqual(response[1], 404)

    def test_player_icon_read_error(self):
        """Return 500 on file read error."""
        icon_file = os.path.join(self.handler.icons_dir, "test.svg")
        os.makedirs(self.handler.icons_dir, exist_ok=True)
        with open(icon_file, "w", encoding="utf-8") as f:
            f.write("<svg></svg>")

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            response = self.handler.handle_player_icon("test")
            self.assertEqual(response[1], 500)

    def test_player_icon_success(self):
        """Return icon SVG content on success."""
        icon_file = os.path.join(self.handler.icons_dir, "test.svg")
        os.makedirs(self.handler.icons_dir, exist_ok=True)
        svg_content = "<svg><circle r='50'/></svg>"
        with open(icon_file, "w", encoding="utf-8") as f:
            f.write(svg_content)

        response = self.handler.handle_player_icon("test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json_data, svg_content)

    def test_set_player_settings_unknown_service(self):
        """Return error for unknown player service."""
        applied, errors = self.handler.set_player_settings("unknown", {})
        self.assertEqual(applied, [])
        self.assertTrue(any("unknown player service" in e for e in errors))

    def test_set_player_settings_invalid_body(self):
        """Reject non-dict values parameter."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                },
                f,
            )
        applied, errors = self.handler.set_player_settings("testsvc", "not a dict")
        self.assertEqual(applied, [])
        self.assertIn("invalid request body", errors)

    def test_set_player_settings_unknown_key(self):
        """Report unknown setting keys."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                    "settings": [
                        {
                            "key": "enabled",
                            "type": "toggle",
                            "label": "Enable",
                            "default": True,
                        }
                    ],
                },
                f,
            )
        applied, errors = self.handler.set_player_settings("testsvc", {"unknown": True})
        self.assertEqual(applied, [])
        self.assertIn("unknown setting: unknown", errors)

    def test_set_player_settings_valid(self):
        """Successfully set valid player settings."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                    "settings": [
                        {
                            "key": "enabled",
                            "type": "toggle",
                            "label": "Enable",
                            "default": True,
                        }
                    ],
                },
                f,
            )
        applied, errors = self.handler.set_player_settings("testsvc", {"enabled": False})
        self.assertEqual(applied, ["enabled"])
        self.assertEqual(errors, [])
        self.configdb_mock.set.assert_called()

    def test_set_player_settings_multiple_values(self):
        """Handle multiple setting updates."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                    "settings": [
                        {
                            "key": "enabled",
                            "type": "toggle",
                            "label": "Enable",
                            "default": True,
                        },
                        {
                            "key": "mode",
                            "type": "select",
                            "label": "Mode",
                            "default": "high",
                            "options": ["low", "high"],
                        },
                    ],
                },
                f,
            )
        applied, errors = self.handler.set_player_settings(
            "testsvc", {"enabled": False, "mode": "low"}
        )
        self.assertEqual(len(applied), 2)
        self.assertEqual(errors, [])
        self.assertEqual(self.configdb_mock.set.call_count, 2)

    def test_handle_set_player_settings_success(self):
        """Handle HTTP request for setting player settings."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                    "settings": [
                        {
                            "key": "enabled",
                            "type": "toggle",
                            "label": "Enable",
                            "default": True,
                        }
                    ],
                },
                f,
            )

        mock_request = Mock()
        mock_request.get_json.return_value = {"enabled": False}
        with patch.object(
            sys.modules["flask"], "request", mock_request
        ), patch("handlers.player_registry_handler.request", mock_request):
            response = self.handler.handle_set_player_settings("testsvc")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json_data["status"], "success")

    def test_handle_set_player_settings_error(self):
        """Return 400 on validation error."""
        json_file = os.path.join(self.handler.players_d_dir, "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "Test",
                    "provided_by": "test",
                    "systemd_service": "testsvc",
                    "icon": "test",
                    "settings": [
                        {
                            "key": "enabled",
                            "type": "toggle",
                            "label": "Enable",
                            "default": True,
                        }
                    ],
                },
                f,
            )

        mock_request = Mock()
        mock_request.get_json.return_value = {"unknown": True}
        with patch.object(
            sys.modules["flask"], "request", mock_request
        ), patch("handlers.player_registry_handler.request", mock_request):
            response = self.handler.handle_set_player_settings("testsvc")
            self.assertEqual(response[1], 400)
            self.assertEqual(response[0].json_data["status"], "error")


if __name__ == "__main__":
    unittest.main()
