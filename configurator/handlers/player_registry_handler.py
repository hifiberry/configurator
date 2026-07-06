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
from typing import Dict, Any, List

try:
    from flask import jsonify, make_response
except ImportError:
    jsonify = None
    make_response = None

logger = logging.getLogger(__name__)

PLAYERS_D_DIR = "/etc/hifiberry/players.d"
ICONS_DIR = os.path.join(PLAYERS_D_DIR, "icons")

# Only allow safe characters in icon names
SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

REQUIRED_FIELDS = ("name", "provided_by", "systemd_service", "icon")

SETTING_TYPES = ("toggle", "select")
_SETTING_REQUIRED = ("key", "type", "label", "default")


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
        # Drop select entries without a non-empty options list
        if entry["type"] == "select":
            options = entry.get("options")
            if not isinstance(options, list) or len(options) == 0:
                continue
        clean.append(entry)
    return clean


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
            out.append({**setting, "value": value})
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
