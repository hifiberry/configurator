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


class PlayerRegistryHandler:
    """Handler for external player discovery and icon serving"""

    def handle_list_players(self):
        """List all external players registered via drop-in descriptors."""
        players: List[Dict[str, Any]] = []

        if not os.path.isdir(PLAYERS_D_DIR):
            return jsonify({"status": "success", "data": {"players": []}})

        for filename in sorted(os.listdir(PLAYERS_D_DIR)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(PLAYERS_D_DIR, filename)
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

            icon_name = descriptor["icon"]
            players.append({
                "name": descriptor["name"],
                "provided_by": descriptor["provided_by"],
                "systemd_service": descriptor["systemd_service"],
                "icon_url": f"/api/v1/players/icon/{icon_name}",
                "allow_change": descriptor.get("allow_change", True),
                "maintainer_name": descriptor.get("maintainer_name", ""),
                "maintainer_url": descriptor.get("maintainer_url", ""),
            })

        return jsonify({"status": "success", "data": {"players": players}})

    def handle_player_icon(self, name: str):
        """Serve an external player icon SVG."""
        if not SAFE_NAME_RE.match(name):
            return jsonify({"status": "error", "message": "Invalid icon name"}), 400

        icon_path = os.path.join(ICONS_DIR, f"{name}.svg")
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
