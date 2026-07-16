#!/usr/bin/env python3
"""Run extension installs as tracked background jobs.

Nothing reaches apt without passing the marker gate first: a package that is
not explicitly marked XB-Hifiberry-Extension: yes cannot be installed, however
the request is spelled.
"""

import logging
import os
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

ACTION_INSTALL = "install"
ACTION_UNINSTALL = "uninstall"
ACTION_REFRESH = "refresh"


class InvalidPackageName(Exception):
    """The package name is not a syntactically valid Debian package name."""


class NotAnExtension(Exception):
    """The package is unknown, or is not marked as a HiFiBerry extension."""


class AptExecutor:
    """Runs apt-get, feeding stdout into the job log and APT::Status-Fd into
    the job's phase/percent.

    apt writes progress to a separate fd, so we read two streams: stdout on
    this thread and the status pipe on another.
    """

    def __init__(self, apt_get: str = APT_GET):
        self.apt_get = apt_get

    def __call__(self, argv: List[str], job: Job) -> int:
        read_fd, write_fd = os.pipe()
        argv = list(argv) + ["-o", f"APT::Status-Fd={write_fd}"]

        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"

        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                pass_fds=(write_fd,),
                env=env,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            os.close(read_fd)
            os.close(write_fd)
            job.append_log(f"Failed to start apt-get: {e}")
            return 127

        # The child owns the write end now; if we hold it open the reader
        # below never sees EOF.
        os.close(write_fd)

        status_thread = threading.Thread(
            target=self._read_status, args=(read_fd, job), daemon=True
        )
        status_thread.start()

        try:
            for line in proc.stdout:
                job.append_log(line.rstrip("\n"))
        finally:
            proc.stdout.close()
            returncode = proc.wait()
            status_thread.join(timeout=5)

        return returncode

    @staticmethod
    def _read_status(read_fd: int, job: Job) -> None:
        try:
            with os.fdopen(read_fd, "r") as status:
                for line in status:
                    parsed = parse_status_line(line)
                    if parsed is None:
                        continue
                    phase, percent, message = parsed
                    job.set_phase(phase, percent)
                    job.append_log(message)
        except Exception as e:
            logger.debug(f"status fd reader stopped: {e}")


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
        return self._start(package, ACTION_UNINSTALL,
                           [self.apt_get, "-y", "remove", package])

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
