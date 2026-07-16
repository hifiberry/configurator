#!/usr/bin/env python3
"""GitHub-release extension sources.

A GitHub source is a repo (``owner/name``) whose latest release ships the
extension ``.deb`` plus an ``extension.json`` catalog card. This is a separate
subsystem from the apt-repo sources: its own storage, catalog, and endpoints.

Security: the trust root is the repo you added. The ``.deb`` is only ever
downloaded from that repo's own release assets (the download URL comes from
GitHub's releases API, not from ``extension.json``), and its sha256 + extension
marker are verified before install.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

GITHUB_SOURCES_DIR = "/etc/hifiberry/extension-sources.d"

# owner/name — GitHub's own allowed character set, one slash.
SAFE_REPO_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]*)/[A-Za-z0-9._-]+$')
SAFE_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


class InvalidGitHubSource(Exception):
    """The GitHub source definition was rejected."""


class GitHubSourceNotFound(InvalidGitHubSource):
    """The requested GitHub source does not exist."""


class GitHubSourceManager:
    """Manages the configured GitHub sources under a drop-in directory."""

    def __init__(self, sources_dir: str = GITHUB_SOURCES_DIR):
        self.sources_dir = sources_dir

    def _source_id(self, repo: str) -> str:
        return repo.replace("/", "-")

    def _path(self, source_id: str) -> str:
        if not source_id or not SAFE_ID_RE.match(source_id):
            raise InvalidGitHubSource(f"Invalid source id: {source_id!r}")
        return os.path.join(self.sources_dir, f"{source_id}.json")

    def list_sources(self):
        sources = []
        if not os.path.isdir(self.sources_dir):
            return sources
        for filename in sorted(os.listdir(self.sources_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.sources_dir, filename)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                repo = data["repo"]
            except (OSError, ValueError, KeyError) as e:
                logger.warning(f"Skipping unreadable GitHub source {path}: {e}")
                continue
            sources.append({"id": filename[:-len(".json")], "repo": repo})
        return sources

    def add_source(self, repo: str):
        if not repo or not SAFE_REPO_RE.match(repo):
            raise InvalidGitHubSource(f"Invalid repository (expected owner/name): {repo!r}")
        os.makedirs(self.sources_dir, exist_ok=True)
        source_id = self._source_id(repo)
        path = self._path(source_id)
        with open(path, "w") as f:
            json.dump({"repo": repo}, f)
        os.chmod(path, 0o644)
        logger.info(f"Added GitHub extension source {source_id}: {repo}")
        return {"id": source_id, "repo": repo}

    def remove_source(self, source_id: str):
        path = self._path(source_id)
        if not os.path.isfile(path):
            raise GitHubSourceNotFound(f"Unknown GitHub source: {source_id}")
        os.remove(path)
        logger.info(f"Removed GitHub extension source {source_id}")
