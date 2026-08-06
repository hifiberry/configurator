#!/usr/bin/env python3
"""
HiFiBerry Configuration API Player Registry Handler

Discovers external players from drop-in descriptor files in
/etc/hifiberry/players.d/ and serves their icons.
"""

import os
import re
import json
import logging
import urllib.request
from urllib.parse import urlparse
from typing import Dict, Any, List

try:
    from flask import jsonify, make_response, request
except ImportError:
    jsonify = None
    make_response = None
    request = None

logger = logging.getLogger(__name__)

PLAYERS_D_DIR = "/etc/hifiberry/players.d"
ICONS_DIR = os.path.join(PLAYERS_D_DIR, "icons")

# Only allow safe characters in icon names
SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

REQUIRED_FIELDS = ("name", "provided_by", "systemd_service", "icon")

SETTING_TYPES = ("toggle", "select", "number")
_SETTING_REQUIRED = ("key", "type", "label", "default")

# A select may source its options from a plugin's own API instead of listing
# them statically, for choices only known at runtime (e.g. AES67 streams
# announced on the network). config-server runs as root, so only loopback URLs
# are accepted -- fetching arbitrary hosts here would be an SSRF.
_ALLOWED_OPTION_HOSTS = ("localhost", "127.0.0.1", "::1")
_OPTIONS_FETCH_TIMEOUT = 2.0


def setting_value_key(systemd_service, key):
    """ConfigDB key for a plugin setting value."""
    return f"player.{systemd_service}.{key}"


def coerce_setting_value(setting_type, raw):
    """Coerce a stored TEXT value (or native value / None) to its typed form."""
    if raw is None:
        return None
    if setting_type == "toggle":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes", "on")
    if setting_type == "number":
        if isinstance(raw, bool):
            return None
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return None
        # Keep whole numbers integral so the UI shows "10", not "10.0".
        return int(number) if number.is_integer() else number
    return str(raw)


def serialize_setting_value(setting_type, value):
    """Serialize a typed value to the TEXT form stored in ConfigDB.

    For type == "toggle", expects value to already be a Python bool;
    callers should coerce with coerce_setting_value first if needed.
    """
    if setting_type == "toggle":
        return "true" if value else "false"
    return str(value)


def sanitize_settings(descriptor):
    """Return the descriptor's declared settings, dropping malformed entries."""
    raw = descriptor.get("settings")
    if not isinstance(raw, list):
        return []
    clean = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if any(f not in entry for f in _SETTING_REQUIRED):
            continue
        if entry["type"] not in SETTING_TYPES:
            continue
        # Drop select entries that offer no way to obtain options at all
        if entry["type"] == "select":
            options = entry.get("options")
            has_static = isinstance(options, list) and len(options) > 0
            if not has_static and not _valid_options_url(entry.get("options_url")):
                continue
        if entry["type"] == "number":
            bounds = _number_bounds(entry)
            if bounds is None:
                continue
            entry = {**entry, **bounds}
        clean.append(entry)
    return clean


def _valid_options_url(url):
    """True for a loopback http(s) URL. See _ALLOWED_OPTION_HOSTS."""
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    return (parsed.hostname or "") in _ALLOWED_OPTION_HOSTS


def _number_bounds(entry):
    """Validated {min, max, step} for a number setting, or None if unusable.

    Bounds are mandatory: without them the UI would happily submit any value,
    and these feed real device configuration.
    """
    raw_min, raw_max = entry.get("min"), entry.get("max")
    raw_step = entry.get("step", 1)
    values = {}
    for name, raw in (("min", raw_min), ("max", raw_max), ("step", raw_step)):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        values[name] = raw
    if values["min"] > values["max"]:
        return None
    if values["step"] <= 0:
        return None
    return values


class PlayerRegistryHandler:
    """Handler for external player discovery and icon serving"""

    def __init__(self, configdb=None, players_d_dir=PLAYERS_D_DIR):
        self.configdb = configdb
        self.players_d_dir = players_d_dir
        self.icons_dir = os.path.join(players_d_dir, "icons")

    def _load_descriptors(self):
        """Load valid descriptor dicts from the players.d directory."""
        descriptors = []
        if not os.path.isdir(self.players_d_dir):
            return descriptors
        for filename in sorted(os.listdir(self.players_d_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.players_d_dir, filename)
            try:
                with open(path, "r") as f:
                    descriptor = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping invalid player descriptor {path}: {e}")
                continue
            if not isinstance(descriptor, dict):
                logger.warning(f"Skipping {path}: not a JSON object")
                continue
            missing = [f for f in REQUIRED_FIELDS if f not in descriptor]
            if missing:
                logger.warning(f"Skipping {path}: missing fields {missing}")
                continue
            descriptors.append(descriptor)
        return descriptors

    def _fetch_json(self, url):
        """GET a loopback URL and return parsed JSON, or None on any failure.

        Split out so tests can stub it; a plugin being down must never break
        the players listing.
        """
        try:
            with urllib.request.urlopen(url, timeout=_OPTIONS_FETCH_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - any failure means "no options"
            logger.debug(f"Could not fetch options from {url}: {e}")
            return None

    def _resolve_options(self, setting, current_value):
        """Options for a select, fetching them if the descriptor names a URL.

        When the source is unreachable the stored value is kept as the sole
        option, so a plugin that is momentarily down does not make the UI look
        as though the user never chose anything.
        """
        static = setting.get("options")
        if isinstance(static, list) and static:
            return static
        url = setting.get("options_url")
        if not _valid_options_url(url):
            return []
        payload = self._fetch_json(url)
        items = payload
        path = setting.get("options_path")
        if isinstance(payload, dict):
            items = payload.get(path) if path else None
        if not isinstance(items, list):
            if current_value:
                return [{"value": current_value, "label": str(current_value)}]
            return []
        value_field = setting.get("options_value")
        label_field = setting.get("options_label", value_field)
        options = []
        for item in items:
            if isinstance(item, dict):
                if not value_field:
                    continue
                value = item.get(value_field)
                label = item.get(label_field, value)
            else:
                value = label = item
            if value is None:
                continue
            options.append({"value": value, "label": str(label)})
        return options

    def _settings_with_values(self, descriptor):
        """Descriptor settings enriched with the current stored value."""
        service = descriptor["systemd_service"]
        out = []
        for setting in sanitize_settings(descriptor):
            value = None
            if self.configdb is not None:
                raw = self.configdb.get(setting_value_key(service, setting["key"]), default=None)
                value = coerce_setting_value(setting["type"], raw)
            if value is None:
                value = setting["default"]
            enriched = {**setting, "value": value}
            if setting["type"] == "select":
                enriched["options"] = self._resolve_options(setting, value)
            out.append(enriched)
        return out

    def _build_players(self):
        players = []
        for descriptor in self._load_descriptors():
            players.append({
                "name": descriptor["name"],
                "provided_by": descriptor["provided_by"],
                "systemd_service": descriptor["systemd_service"],
                "icon_url": f"/api/v1/players/icon/{descriptor['icon']}",
                "allow_change": descriptor.get("allow_change", True),
                "maintainer_name": descriptor.get("maintainer_name", ""),
                "maintainer_url": descriptor.get("maintainer_url", ""),
                "settings": self._settings_with_values(descriptor),
            })
        return players

    def handle_list_players(self):
        """List all external players registered via drop-in descriptors."""
        return jsonify({"status": "success", "data": {"players": self._build_players()}})

    def handle_player_icon(self, name: str):
        """Serve an external player icon SVG."""
        if not SAFE_NAME_RE.match(name):
            return jsonify({"status": "error", "message": "Invalid icon name"}), 400

        icon_path = os.path.join(self.icons_dir, f"{name}.svg")
        if not os.path.isfile(icon_path):
            return jsonify({"status": "error", "message": "Icon not found"}), 404

        try:
            with open(icon_path, "r") as f:
                svg_data = f.read()
            response = make_response(svg_data)
            response.headers["Content-Type"] = "image/svg+xml"
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
        except OSError as e:
            logger.error(f"Error reading icon {icon_path}: {e}")
            return jsonify({"status": "error", "message": "Failed to read icon"}), 500

    def set_player_settings(self, systemd_service, values):
        """Validate and persist setting values for one plugin.

        Returns (applied_keys, errors)."""
        descriptor = next(
            (d for d in self._load_descriptors() if d["systemd_service"] == systemd_service),
            None,
        )
        if descriptor is None:
            return [], [f"unknown player service: {systemd_service}"]

        # Guard against non-dict bodies (list, string, number, etc.)
        if not isinstance(values, dict):
            return [], ["invalid request body"]

        allowed = {s["key"]: s for s in sanitize_settings(descriptor)}
        applied, errors = [], []
        for key, value in values.items():
            setting = allowed.get(key)
            if setting is None:
                errors.append(f"unknown setting: {key}")
                continue
            if setting["type"] == "number":
                number = coerce_setting_value("number", value)
                if number is None:
                    errors.append(f"{key}: not a number")
                    continue
                if not (setting["min"] <= number <= setting["max"]):
                    errors.append(
                        f"{key}: out of range ({setting['min']}..{setting['max']})")
                    continue
                value = number
            self.configdb.set(
                setting_value_key(systemd_service, key),
                serialize_setting_value(setting["type"], coerce_setting_value(setting["type"], value)),
            )
            applied.append(key)
        return applied, errors

    def handle_set_player_settings(self, systemd_service):
        """Flask handler: persist submitted player settings."""
        values = request.get_json(silent=True) or {}
        applied, errors = self.set_player_settings(systemd_service, values)
        if not applied and errors:
            return jsonify({"status": "error", "message": "; ".join(errors)}), 400
        return jsonify({"status": "success",
                        "data": {"applied": applied, "errors": errors}})
