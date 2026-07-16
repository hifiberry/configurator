#!/usr/bin/env python3
"""Run extension installs as tracked background jobs.

Nothing reaches apt without passing the marker gate first: a package that is
not explicitly marked XB-Hifiberry-Extension: yes cannot be installed, however
the request is spelled.
"""

import logging
import subprocess
import threading
from typing import Callable, List, Optional

from .aptstatus import parse_status_line
from .catalog import VALID_PACKAGE_RE, ExtensionCatalog
from .jobs import (
    Job,
    JobRegistry,
    PHASE_DONE,
    PHASE_DOWNLOADING,
    PHASE_FAILED,
)
from .postinstall import refresh_system_state

logger = logging.getLogger(__name__)

APT_GET = "/usr/bin/apt-get"
SYSTEMD_RUN = "/usr/bin/systemd-run"

ACTION_INSTALL = "install"
ACTION_UNINSTALL = "uninstall"
ACTION_REFRESH = "refresh"


class InvalidPackageName(Exception):
    """The package name is not a syntactically valid Debian package name."""


class NotAnExtension(Exception):
    """The package is unknown, or is not marked as a HiFiBerry extension."""


class AptExecutor:
    """Runs apt-get as a transient systemd unit via systemd-run.

    config-server's own unit bounds capabilities to CAP_SYS_ADMIN, which strips
    CAP_SETUID/SETGID (so apt cannot drop to its ``_apt`` sandbox user —
    "seteuid 42 failed - Operation not permitted") and CAP_DAC_OVERRIDE (so even
    as root it cannot reach the ``_apt``-owned apt lists). Running apt directly
    from config-server therefore fails on any real device. systemd-run hands the
    work to PID 1, which starts a transient unit with the full root capability
    set, so apt and dpkg maintainer scripts run unrestricted without widening
    config-server's own bounding set.

    apt's machine-readable progress is routed to stdout with
    ``APT::Status-Fd=1`` and interleaved with its normal output: lines that
    parse as status updates drive the job's phase/percent, everything else is
    logged. This keeps everything on one stream, so no extra fd needs to survive
    the systemd-run boundary (systemd-run does not forward arbitrary fds).
    """

    def __init__(self, apt_get: str = APT_GET, systemd_run: str = SYSTEMD_RUN):
        self.apt_get = apt_get
        self.systemd_run = systemd_run

    def __call__(self, argv: List[str], job: Job) -> int:
        cmd = [
            self.systemd_run,
            "--pipe", "--wait", "--collect", "--quiet",
            "--setenv=DEBIAN_FRONTEND=noninteractive",
        ] + list(argv) + ["-o", "APT::Status-Fd=1"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            job.append_log(f"Failed to start systemd-run: {e}")
            return 127

        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                parsed = parse_status_line(line)
                if parsed is not None:
                    phase, percent, message = parsed
                    job.set_phase(phase, percent)
                    job.append_log(message)
                elif line:
                    job.append_log(line)
        finally:
            proc.stdout.close()
            returncode = proc.wait()

        return returncode


def _default_thread_factory(target):
    return threading.Thread(target=target, daemon=True)


class ExtensionRunner:
    def __init__(self, catalog: ExtensionCatalog, jobs: JobRegistry,
                 executor: Optional[Callable[[List[str], Job], int]] = None,
                 refresher: Optional[Callable[[], object]] = None,
                 thread_factory: Optional[Callable] = None,
                 apt_get: str = APT_GET):
        self.catalog = catalog
        self.jobs = jobs
        self.executor = executor or AptExecutor(apt_get)
        self.refresher = refresher or refresh_system_state
        self.thread_factory = thread_factory or _default_thread_factory
        self.apt_get = apt_get

    # -- gate ------------------------------------------------------------

    def _require_extension(self, package: str) -> None:
        """The security boundary. Nothing reaches apt without passing here."""
        if not package or not VALID_PACKAGE_RE.match(package):
            raise InvalidPackageName(f"Invalid package name: {package!r}")
        if self.catalog.get_extension(package) is None:
            raise NotAnExtension(
                f"{package} is not a HiFiBerry extension"
            )

    # -- public API ------------------------------------------------------

    def install(self, package: str) -> Job:
        self._require_extension(package)
        return self._start(package, ACTION_INSTALL,
                           [self.apt_get, "-y", "install", package])

    def uninstall(self, package: str) -> Job:
        self._require_extension(package)
        # purge, not remove: an extension's registrations live in conffiles under
        # /etc (players.d, configserver conf.d) that `remove` would leave behind,
        # stranding a dangling player entry. purge also runs the postrm purge
        # branch, so an extension can clean up what it built (e.g. a Docker image).
        return self._start(package, ACTION_UNINSTALL,
                           [self.apt_get, "-y", "purge", package])

    def refresh(self) -> Job:
        return self._start(None, ACTION_REFRESH, [self.apt_get, "update"],
                           refresh_after=False)

    # -- internals -------------------------------------------------------

    def _start(self, package, action, argv, refresh_after=True) -> Job:
        job = self.jobs.create(package, action)

        def run():
            self._execute(job, argv, refresh_after)

        self.thread_factory(run).start()
        return job

    def _execute(self, job: Job, argv: List[str], refresh_after: bool) -> None:
        job.set_phase(PHASE_DOWNLOADING, 0)
        try:
            returncode = self.executor(argv, job)
        except Exception as e:
            logger.exception("Extension operation crashed")
            job.finish(PHASE_FAILED, exit_code=None, error=str(e))
            return

        if returncode != 0:
            job.finish(PHASE_FAILED, exit_code=returncode,
                       error=f"{job.action} failed with exit code {returncode}")
            return

        if refresh_after:
            try:
                self.refresher()
            except Exception as e:
                # The package is installed; a refresh failure must not be
                # reported as an install failure.
                logger.warning(f"Post-install refresh failed: {e}")
                job.append_log(f"Warning: post-install refresh failed: {e}")

        job.finish(PHASE_DONE, exit_code=0)
