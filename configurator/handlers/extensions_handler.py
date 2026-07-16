#!/usr/bin/env python3
"""HiFiBerry Configuration API Extensions Handler

Thin Flask wrappers over configurator.extensions. All logic lives there; this
module only maps exceptions onto HTTP status codes.
"""

import logging
import os

try:
    from flask import jsonify, request
except ImportError:
    # Flask not available - likely during testing or installation
    jsonify = None
    request = None

from ..extensions.catalog import ExtensionCatalog
from ..extensions.github import (
    GitHubCatalog,
    GitHubSourceManager,
    GitHubSourceNotFound,
    InvalidGitHubSource,
)
from ..extensions.jobs import ExtensionBusy, JobRegistry, TERMINAL_PHASES
from ..extensions.runner import ExtensionRunner, InvalidPackageName, NotAnExtension
from ..extensions.sources import InvalidSource, SourceManager, SourceNotFound

logger = logging.getLogger(__name__)

REBOOT_FLAG_PATH = "/run/reboot-required"


class ExtensionsHandler:
    """Handler for extension catalog, installation and source management."""

    def __init__(self, catalog=None, jobs=None, runner=None, sources=None,
                 github_sources=None, github_catalog=None,
                 service_manager=None, reboot_flag_path=REBOOT_FLAG_PATH):
        self.catalog = catalog or ExtensionCatalog()
        self.jobs = jobs or JobRegistry()
        self.sources = sources or SourceManager()
        self.github_sources = github_sources or GitHubSourceManager()
        self.github_catalog = github_catalog or GitHubCatalog(self.github_sources)
        self.reboot_flag_path = reboot_flag_path
        if runner is not None:
            self.runner = runner
        else:
            refresher = None
            if service_manager is not None:
                from ..extensions.postinstall import refresh_system_state
                refresher = lambda: refresh_system_state(service_manager=service_manager)
            self.runner = ExtensionRunner(
                catalog=self.catalog, jobs=self.jobs, refresher=refresher
            )

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _error(message, status):
        return jsonify({"status": "error", "message": message}), status

    @staticmethod
    def _job_accepted(job):
        return jsonify({"status": "success", "data": {"job": job.to_dict()}}), 202

    def _start(self, operation, *args):
        try:
            job = operation(*args)
        except InvalidPackageName as e:
            return self._error(str(e), 400)
        except NotAnExtension as e:
            return self._error(str(e), 403)
        except ExtensionBusy as e:
            return self._error(str(e), 409)
        except Exception as e:
            logger.exception("Failed to start extension operation")
            return self._error(str(e), 500)
        return self._job_accepted(job)

    # -- catalog ---------------------------------------------------------

    def handle_list_extensions(self):
        """List extensions from both apt repos and GitHub sources.

        The two catalogs are read independently so a failing GitHub source (or no
        network) never blanks the apt catalog, and vice versa. On a duplicate
        package the apt entry wins (read first).
        """
        extensions = []
        seen = set()
        for catalog, label in ((self.catalog, "apt"), (self.github_catalog, "github")):
            try:
                for ext in catalog.list_extensions():
                    if ext.package in seen:
                        logger.info(f"{ext.package} in multiple sources; keeping the apt one")
                        continue
                    seen.add(ext.package)
                    extensions.append(ext.to_dict())
            except Exception as e:
                logger.exception(f"Failed to read {label} catalog: {e}")
        return jsonify({
            "status": "success",
            "data": {"extensions": extensions},
            "count": len(extensions),
        })

    def _find_extension(self, package: str):
        """The catalog entry for a package (apt preferred, then GitHub), or None."""
        try:
            ext = self.catalog.get_extension(package)
            if ext is not None:
                return ext
        except Exception:
            logger.exception("apt catalog lookup failed")
        try:
            return self.github_catalog.get_extension(package)
        except Exception:
            logger.exception("github catalog lookup failed")
            return None

    def handle_get_extension(self, package: str):
        extension = self._find_extension(package)
        if extension is None:
            return self._error(f"{package} is not a HiFiBerry extension", 404)
        return jsonify({"status": "success", "data": extension.to_dict()})

    # -- operations ------------------------------------------------------

    def handle_install(self, package: str):
        # A GitHub extension installs from its downloaded release asset; anything
        # else goes through the apt path (which gates on the apt catalog).
        try:
            github_ext = self.github_catalog.get_extension(package)
        except Exception:
            logger.exception("github catalog lookup failed during install")
            github_ext = None
        if github_ext is not None:
            return self._start(self.runner.install_github, package,
                               github_ext.download_url, github_ext.sha256)
        return self._start(self.runner.install, package)

    def handle_uninstall(self, package: str):
        return self._start(self.runner.uninstall, package)

    def handle_refresh(self):
        return self._start(self.runner.refresh)

    def handle_get_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if job is None:
            return self._error(f"Unknown job: {job_id}", 404)
        data = job.to_dict()
        # Debian convention: a maintainer script touches this if its changes
        # need a reboot. Only meaningful once the job is finished.
        reboot_required = (
            data["phase"] in TERMINAL_PHASES
            and os.path.exists(self.reboot_flag_path)
        )
        return jsonify({
            "status": "success",
            "data": {"job": data, "reboot_required": reboot_required},
        })

    # -- sources ---------------------------------------------------------

    def handle_list_sources(self):
        try:
            sources = self.sources.list_sources()
        except Exception as e:
            logger.exception("Failed to list sources")
            return self._error(str(e), 500)
        return jsonify({
            "status": "success",
            "data": {"sources": sources},
            "count": len(sources),
        })

    def handle_add_source(self):
        payload = request.get_json(silent=True) or {}
        required = ("id", "uri", "suite", "components", "key")
        missing = [f for f in required if not payload.get(f)]
        if missing:
            return self._error(f"Missing required fields: {', '.join(missing)}", 400)

        try:
            source = self.sources.add_source(
                payload["id"], payload["uri"], payload["suite"],
                payload["components"], payload["key"],
            )
        except InvalidSource as e:
            return self._error(str(e), 400)
        except Exception as e:
            logger.exception("Failed to add source")
            return self._error(str(e), 500)

        logger.info(f"Extension source added via API: {source['id']} -> {source['uri']}")
        return jsonify({"status": "success", "data": {"source": source}}), 201

    def handle_remove_source(self, source_id: str):
        try:
            self.sources.remove_source(source_id)
        except SourceNotFound as e:
            return self._error(str(e), 404)
        except InvalidSource as e:
            return self._error(str(e), 400)
        except Exception as e:
            logger.exception("Failed to remove source")
            return self._error(str(e), 500)
        return jsonify({
            "status": "success",
            "message": f"Removed source {source_id}",
        })

    # -- GitHub sources (separate from apt sources) ----------------------

    def handle_list_github_sources(self):
        try:
            sources = self.github_sources.list_sources()
        except Exception as e:
            logger.exception("Failed to list GitHub sources")
            return self._error(str(e), 500)
        return jsonify({
            "status": "success",
            "data": {"sources": sources},
            "count": len(sources),
        })

    def handle_add_github_source(self):
        payload = request.get_json(silent=True) or {}
        repo = payload.get("repo")
        if not repo:
            return self._error("Missing required field: repo", 400)
        try:
            source = self.github_sources.add_source(repo)
        except InvalidGitHubSource as e:
            return self._error(str(e), 400)
        except Exception as e:
            logger.exception("Failed to add GitHub source")
            return self._error(str(e), 500)
        logger.info(f"GitHub extension source added via API: {source['repo']}")
        return jsonify({"status": "success", "data": {"source": source}}), 201

    def handle_remove_github_source(self, source_id: str):
        try:
            self.github_sources.remove_source(source_id)
        except GitHubSourceNotFound as e:
            return self._error(str(e), 404)
        except InvalidGitHubSource as e:
            return self._error(str(e), 400)
        except Exception as e:
            logger.exception("Failed to remove GitHub source")
            return self._error(str(e), 500)
        return jsonify({
            "status": "success",
            "message": f"Removed GitHub source {source_id}",
        })
