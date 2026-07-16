#!/usr/bin/env python3
"""Manage the apt sources that supply extensions.

A source IS a catalog: adding a repo is how a user adds extensions. Because
these strings are written into a config file that root's apt parses, every
field is validated against a strict allowlist pattern first.

Unsigned repos are refused. A repo without a key is a MITM waiting to happen,
and refusing costs the user nothing.
"""

import logging
import os
import re
import subprocess
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SOURCES_DIR = "/etc/apt/sources.list.d"
KEYRINGS_DIR = "/usr/share/keyrings"
FILE_PREFIX = "hifiberry-ext-"

SAFE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')
SAFE_URI_RE = re.compile(r'^https?://[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]+$')
SAFE_SUITE_RE = re.compile(r'^[A-Za-z0-9._-]+$')
SAFE_COMPONENTS_RE = re.compile(r'^[A-Za-z0-9._-]+( [A-Za-z0-9._-]+)*$')

PGP_HEADER = "-----BEGIN PGP PUBLIC KEY BLOCK-----"

# deb [signed-by=<keyring>] <uri> <suite> <components>
_LIST_LINE_RE = re.compile(
    r'^deb\s+\[signed-by=(?P<keyring>[^\]]+)\]\s+'
    r'(?P<uri>\S+)\s+(?P<suite>\S+)\s+(?P<components>.+?)\s*$'
)


class InvalidSource(Exception):
    """The source definition was rejected."""


def _gpg_dearmor(armored: str) -> bytes:
    result = subprocess.run(
        ["gpg", "--dearmor"],
        input=armored.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        raise InvalidSource(
            f"Could not dearmor key: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


class SourceManager:
    def __init__(self, sources_dir: str = SOURCES_DIR,
                 keyrings_dir: str = KEYRINGS_DIR,
                 dearmor: Optional[Callable[[str], bytes]] = None):
        self.sources_dir = sources_dir
        self.keyrings_dir = keyrings_dir
        self._dearmor = dearmor or _gpg_dearmor

    # -- paths -----------------------------------------------------------

    def _validate_id(self, source_id: str) -> str:
        if not source_id or not SAFE_ID_RE.match(source_id):
            raise InvalidSource(f"Invalid source id: {source_id!r}")
        return source_id

    def _list_path(self, source_id: str) -> str:
        return os.path.join(self.sources_dir, f"{FILE_PREFIX}{source_id}.list")

    def _keyring_path(self, source_id: str) -> str:
        return os.path.join(self.keyrings_dir, f"{FILE_PREFIX}{source_id}.gpg")

    # -- public API ------------------------------------------------------

    def list_sources(self) -> List[Dict]:
        """List only sources we manage. Unmanaged files are none of our
        business and must never be removable through this API."""
        sources = []
        if not os.path.isdir(self.sources_dir):
            return sources

        for filename in sorted(os.listdir(self.sources_dir)):
            if not filename.startswith(FILE_PREFIX) or not filename.endswith(".list"):
                continue
            source_id = filename[len(FILE_PREFIX):-len(".list")]
            path = os.path.join(self.sources_dir, filename)
            try:
                with open(path, "r") as f:
                    content = f.read()
            except OSError as e:
                logger.warning(f"Cannot read source {path}: {e}")
                continue

            for line in content.splitlines():
                match = _LIST_LINE_RE.match(line.strip())
                if not match:
                    continue
                sources.append({
                    "id": source_id,
                    "uri": match.group("uri"),
                    "suite": match.group("suite"),
                    "components": match.group("components"),
                    "keyring": match.group("keyring"),
                })
                break
        return sources

    def add_source(self, source_id: str, uri: str, suite: str,
                   components: str, key_armored: str) -> Dict:
        source_id = self._validate_id(source_id)

        if not uri or not SAFE_URI_RE.match(uri):
            raise InvalidSource(f"Invalid repository URI: {uri!r}")
        if not suite or not SAFE_SUITE_RE.match(suite):
            raise InvalidSource(f"Invalid suite: {suite!r}")
        if not components or not SAFE_COMPONENTS_RE.match(components):
            raise InvalidSource(f"Invalid components: {components!r}")
        if not key_armored or PGP_HEADER not in key_armored:
            raise InvalidSource(
                "A signing key is required; unsigned repositories are not allowed"
            )

        # Dearmor before writing anything, so a bad key leaves no trace.
        keyring_bytes = self._dearmor(key_armored)

        keyring_path = self._keyring_path(source_id)
        with open(keyring_path, "wb") as f:
            f.write(keyring_bytes)
        os.chmod(keyring_path, 0o644)  # apt reads this as _apt, not root

        list_path = self._list_path(source_id)
        with open(list_path, "w") as f:
            f.write(f"deb [signed-by={keyring_path}] {uri} {suite} {components}\n")
        os.chmod(list_path, 0o644)

        logger.info(f"Added extension source {source_id}: {uri} {suite} {components}")
        return {
            "id": source_id,
            "uri": uri,
            "suite": suite,
            "components": components,
            "keyring": keyring_path,
        }

    def remove_source(self, source_id: str) -> None:
        source_id = self._validate_id(source_id)
        list_path = self._list_path(source_id)
        if not os.path.isfile(list_path):
            raise InvalidSource(f"Unknown source: {source_id}")

        os.remove(list_path)
        keyring_path = self._keyring_path(source_id)
        if os.path.isfile(keyring_path):
            os.remove(keyring_path)
        logger.info(f"Removed extension source {source_id}")
