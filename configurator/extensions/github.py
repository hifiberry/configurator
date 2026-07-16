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
import subprocess
import time
import urllib.request

from .catalog import (
    DEFAULT_CATEGORY,
    DEFAULT_NEEDS_REBOOT,
    Extension,
    VALID_CATEGORIES,
    VALID_NEEDS_REBOOT,
    VALID_PACKAGE_RE,
    _split_description,
    _state,
)

logger = logging.getLogger(__name__)

GITHUB_SOURCES_DIR = "/etc/hifiberry/extension-sources.d"
GITHUB_API = "https://api.github.com"
USER_AGENT = "hifiberry-configurator"

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


class _UrllibFetcher:
    """Production fetcher: plain HTTPS GETs against the GitHub API / assets."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _open(self, url: str):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        })
        return urllib.request.urlopen(req, timeout=self.timeout)

    def get_json(self, url: str):
        with self._open(url) as resp:
            return json.load(resp)

    def get_bytes(self, url: str) -> bytes:
        with self._open(url) as resp:
            return resp.read()


def urllib_fetcher():
    return _UrllibFetcher()


def dpkg_installed_version(package: str):
    """Installed version of a dpkg package, or None if not installed."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", package],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"dpkg-query for {package} failed: {e}")
    return None


class GitHubCatalog:
    """Builds catalog entries from the latest release of each GitHub source."""

    def __init__(self, source_manager, fetcher=None, installed_version=None,
                 clock=time.time, cache_ttl: int = 60):
        self.source_manager = source_manager
        self.fetcher = fetcher or urllib_fetcher()
        self.installed_version = installed_version or dpkg_installed_version
        self.clock = clock
        self.cache_ttl = cache_ttl
        self._cache = {}  # repo -> (timestamp, release_json)

    def _release(self, repo: str):
        now = self.clock()
        cached = self._cache.get(repo)
        if cached is not None and now - cached[0] < self.cache_ttl:
            return cached[1]
        owner, name = repo.split("/", 1)
        release = self.fetcher.get_json(
            f"{GITHUB_API}/repos/{owner}/{name}/releases/latest")
        self._cache[repo] = (now, release)
        return release

    def _build(self, repo: str, release) -> Extension:
        assets = {a.get("name"): a for a in release.get("assets", [])}
        meta_asset = assets.get("extension.json")
        if meta_asset is None:
            raise ValueError("release has no extension.json asset")
        meta = json.loads(self.fetcher.get_bytes(meta_asset["browser_download_url"]))

        package = str(meta.get("package", ""))
        if not VALID_PACKAGE_RE.match(package):
            raise ValueError(f"invalid package name: {package!r}")

        # The download must come from an asset in *this* release, matched by the
        # filename in extension.json — never a URL that extension.json could
        # point at another host.
        deb_asset = assets.get(meta.get("deb"))
        if deb_asset is None:
            raise ValueError(f"deb asset {meta.get('deb')!r} not in release")

        category = str(meta.get("category", "")).strip().lower()
        if category not in VALID_CATEGORIES:
            category = DEFAULT_CATEGORY
        needs_reboot = str(meta.get("needs_reboot", "")).strip().lower()
        if needs_reboot not in VALID_NEEDS_REBOOT:
            needs_reboot = DEFAULT_NEEDS_REBOOT

        summary, description = _split_description(str(meta.get("description", "")))
        version = meta.get("version")
        installed = self.installed_version(package)

        # Only a full URL is usable as an icon before install (the players.d icon
        # file doesn't exist yet); a bare icon name falls back to the category.
        icon = str(meta.get("icon", "")).strip()
        icon_url = icon if icon.startswith(("http://", "https://")) else None

        return Extension(
            package=package,
            name=str(meta.get("name", "")).strip() or package,
            category=category,
            summary=summary,
            description=description,
            version=version,
            installed_version=installed,
            state=_state(version, installed),
            needs_reboot=needs_reboot,
            icon_url=icon_url,
            source=f"github:{repo}",
            download_url=deb_asset["browser_download_url"],
            sha256=str(meta.get("sha256", "")) or None,
        )

    def list_extensions(self):
        out = []
        for src in self.source_manager.list_sources():
            repo = src["repo"]
            try:
                out.append(self._build(repo, self._release(repo)))
            except Exception as e:  # one bad source must not break the catalog
                logger.warning(f"Skipping GitHub source {repo}: {e}")
        return out

    def get_extension(self, package: str):
        for ext in self.list_extensions():
            if ext.package == package:
                return ext
        return None
