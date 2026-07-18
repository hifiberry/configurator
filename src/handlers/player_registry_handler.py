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
from typing import Dict, Any, List, Optional, Union, Tuple, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Response

try:
    from flask import jsonify, make_response, request
except ImportError:
    jsonify = None  # type: ignore[assignment]
    make_response = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

PLAYERS_D_DIR = "/etc/hifiberry/players.d"
ICONS_DIR = os.path.join(PLAYERS_D_DIR, "icons")

# Only allow safe characters in icon names
SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

REQUIRED_FIELDS = ("name", "provided_by", "systemd_service", "icon")

SETTING_TYPES = ("toggle", "select")
_SETTING_REQUIRED = ("key", "type", "label", "default")


def setting_value_key(systemd_service: str, key: str) -> str:
    """ConfigDB key for a plugin setting value."""
    return f"player.{systemd_service}.{key}"


def coerce_setting_value(setting_type: str, raw: Any) -> Optional[Union[bool, str]]:
    """Coerce a stored TEXT value (or native value / None) to its typed form."""
    if raw is None:
        return None
    if setting_type == "toggle":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes", "on")
    return str(raw)


def serialize_setting_value(setting_type: str, value: Any) -> str:
    """Serialize a typed value to the TEXT form stored in ConfigDB.

    For type == "toggle", expects value to already be a Python bool;
    callers should coerce with coerce_setting_value first if needed.
    """
    if setting_type == "toggle":
        return "true" if value else "false"
    return str(value)


def sanitize_settings(descriptor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the descriptor's declared settings, dropping malformed entries."""
    raw: Any = descriptor.get("settings")
    if not isinstance(raw, list):
        return []
    clean: List[Dict[str, Any]] = []
    for entry in raw:  # type: ignore[attr-defined]
        if not isinstance(entry, dict):
            continue
        entry = cast(Dict[str, Any], entry)
        if any(f not in entry for f in _SETTING_REQUIRED):
            continue
        if entry["type"] not in SETTING_TYPES:
            continue
        # Drop select entries without a non-empty options list
        if entry["type"] == "select":
            options: Any = entry.get("options")
            if not isinstance(options, list) or len(cast(List[Any], options)) == 0:
                continue
        clean.append(entry)
    return clean


class PlayerRegistryHandler:
    """Handler for external player discovery and icon serving"""

    def __init__(self, configdb: Optional[Any] = None, players_d_dir: str = PLAYERS_D_DIR) -> None:
        self.configdb = configdb
        self.players_d_dir = players_d_dir
        self.icons_dir = os.path.join(players_d_dir, "icons")

    def _load_descriptors(self) -> List[Dict[str, Any]]:
        """Load valid descriptor dicts from the players.d directory."""
        descriptors: List[Dict[str, Any]] = []
        if not os.path.isdir(self.players_d_dir):
            return descriptors
        for filename in sorted(os.listdir(self.players_d_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.players_d_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    descriptor: Any = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Skipping invalid player descriptor %s: %s", path, e)
                continue
            if not isinstance(descriptor, dict):
                logger.warning("Skipping %s: not a JSON object", path)
                continue
            missing: List[str] = [f for f in REQUIRED_FIELDS if f not in descriptor]
            if missing:
                logger.warning("Skipping %s: missing fields %s", path, missing)
                continue
            descriptors.append(cast(Dict[str, Any], descriptor))
        return descriptors

    def _settings_with_values(self, descriptor: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Descriptor settings enriched with the current stored value."""
        service: str = descriptor["systemd_service"]
        out: List[Dict[str, Any]] = []
        for setting in sanitize_settings(descriptor):
            value: Optional[Union[bool, str]] = None
            if self.configdb is not None:
                setting_key = setting_value_key(service, setting["key"])
                raw: Any = self.configdb.get(setting_key, default=None)
                value = coerce_setting_value(setting["type"], raw)
            if value is None:
                value = setting["default"]
            out.append(cast(Dict[str, Any], {**setting, "value": value}))
        return out

    def _build_players(self) -> List[Dict[str, Any]]:
        players: List[Dict[str, Any]] = []
        for descriptor in self._load_descriptors():
            icon_url = f"/api/v1/players/icon/{descriptor['icon']}"
            player_entry: Dict[str, Any] = {
                "name": descriptor["name"],
                "provided_by": descriptor["provided_by"],
                "systemd_service": descriptor["systemd_service"],
                "icon_url": icon_url,
                "allow_change": descriptor.get("allow_change", True),
                "maintainer_name": descriptor.get("maintainer_name", ""),
                "maintainer_url": descriptor.get("maintainer_url", ""),
                "settings": self._settings_with_values(descriptor),
            }
            players.append(player_entry)
        return players

    def handle_list_players(self) -> 'Union[Response, tuple[Response, int]]':
        """List all external players registered via drop-in descriptors."""
        players = self._build_players()
        return jsonify({
            "status": "success",
            "data": {"players": players}
        })  # type: ignore[return-value]

    def handle_player_icon(self, name: str) -> 'Union[Response, tuple[Response, int]]':
        """Serve an external player icon SVG."""
        if not SAFE_NAME_RE.match(name):
            err_msg = "Invalid icon name"
            return jsonify(
                {"status": "error", "message": err_msg}
            ), 400  # type: ignore[return-value]

        icon_path: str = os.path.join(self.icons_dir, f"{name}.svg")
        if not os.path.isfile(icon_path):
            err_msg = "Icon not found"
            return jsonify(
                {"status": "error", "message": err_msg}
            ), 404  # type: ignore[return-value]

        try:
            with open(icon_path, "r", encoding="utf-8") as f:
                svg_data: str = f.read()
            response: Any = make_response(svg_data)  # type: ignore[assignment]
            response.headers["Content-Type"] = "image/svg+xml"
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
        except OSError as e:
            logger.error("Error reading icon %s: %s", icon_path, e)
            err_msg = "Failed to read icon"
            return jsonify(
                {"status": "error", "message": err_msg}
            ), 500  # type: ignore[return-value]

    def set_player_settings(
        self, systemd_service: str, values: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        """Validate and persist setting values for one plugin.

        Returns (applied_keys, errors)."""
        descriptor: Optional[Dict[str, Any]] = next(
            (d for d in self._load_descriptors()
             if d["systemd_service"] == systemd_service),
            None,
        )
        if descriptor is None:
            return [], [f"unknown player service: {systemd_service}"]

        # Guard against non-dict bodies (list, string, number, etc.)
        if not isinstance(values, dict):  # type: ignore[arg-type]
            return [], ["invalid request body"]

        allowed: Dict[str, Dict[str, Any]] = {
            s["key"]: s for s in sanitize_settings(descriptor)
        }
        applied: List[str] = []
        errors: List[str] = []
        for key, value in values.items():
            setting: Optional[Dict[str, Any]] = allowed.get(key)
            if setting is None:
                errors.append(f"unknown setting: {key}")
                continue
            coerced = coerce_setting_value(setting["type"], value)
            serialized = serialize_setting_value(setting["type"], coerced)
            self.configdb.set(  # type: ignore[union-attr]
                setting_value_key(systemd_service, key),
                serialized,
            )
            applied.append(key)
        return applied, errors

    def handle_set_player_settings(
        self, systemd_service: str
    ) -> 'Union[Response, tuple[Response, int]]':
        """Flask handler: persist submitted player settings."""
        json_data = request.get_json(silent=True) or {}  # type: ignore[union-attr]
        values: Dict[str, Any] = cast(Dict[str, Any], json_data)
        applied, errors = self.set_player_settings(systemd_service, values)
        if not applied and errors:
            error_msg = "; ".join(errors)
            return jsonify(
                {"status": "error", "message": error_msg}
            ), 400  # type: ignore[return-value]
        return jsonify({
            "status": "success",
            "data": {"applied": applied, "errors": errors}
        })  # type: ignore[return-value]
