from configurator.handlers.player_registry_handler import (
    setting_value_key,
    coerce_setting_value,
    serialize_setting_value,
    sanitize_settings,
)


def test_setting_value_key_namespaces_by_service():
    assert setting_value_key("analog-recognition", "songrec_enabled") == \
        "player.analog-recognition.songrec_enabled"


def test_coerce_toggle_from_stored_strings():
    assert coerce_setting_value("toggle", "true") is True
    assert coerce_setting_value("toggle", "false") is False
    assert coerce_setting_value("toggle", "1") is True
    assert coerce_setting_value("toggle", True) is True
    assert coerce_setting_value("toggle", None) is None


def test_coerce_select_returns_string_or_none():
    assert coerce_setting_value("select", "medium") == "medium"
    assert coerce_setting_value("select", None) is None


def test_serialize_toggle_uses_true_false_strings():
    assert serialize_setting_value("toggle", True) == "true"
    assert serialize_setting_value("toggle", False) == "false"
    assert serialize_setting_value("select", "high") == "high"


def test_sanitize_settings_drops_invalid_and_keeps_valid():
    descriptor = {
        "settings": [
            {"key": "songrec_enabled", "type": "toggle", "label": "Recognize", "default": True},
            {"key": "bad_no_type", "label": "x", "default": 1},
            {"key": "mode", "type": "select", "label": "Mode", "default": "a",
             "options": [{"value": "a", "label": "A"}]},
            {"key": "bad_type", "type": "slider", "label": "y", "default": 1},
        ]
    }
    out = sanitize_settings(descriptor)
    keys = [s["key"] for s in out]
    assert keys == ["songrec_enabled", "mode"]
    assert out[0]["type"] == "toggle"


def test_sanitize_settings_absent_is_empty():
    assert sanitize_settings({"name": "x"}) == []
