#!/usr/bin/env python3
"""In-memory job tracking for extension installs.

Installs take minutes (a ~180MB download plus, for some extensions, a
container build) while nginx gives us 60s. So the API hands back a job id and
the UI polls it.

Jobs are deliberately in-memory and do not survive a restart: the install path
must never restart config-server, because that would destroy the very job the
UI is polling.
"""

import threading
import time
import uuid
from collections import deque
from typing import Optional

PHASE_QUEUED = "queued"
PHASE_DOWNLOADING = "downloading"
PHASE_INSTALLING = "installing"
PHASE_CONFIGURING = "configuring"
PHASE_DONE = "done"
PHASE_FAILED = "failed"

TERMINAL_PHASES = frozenset({PHASE_DONE, PHASE_FAILED})

DEFAULT_MAX_LOG_LINES = 200


class ExtensionBusy(Exception):
    """Another extension operation is already running."""


class Job:
    def __init__(self, job_id, package, action, clock, max_log_lines):
        self.id = job_id
        self.package = package
        self.action = action
        self.phase = PHASE_QUEUED
        self.percent = 0
        self.exit_code = None
        self.error = None
        self.started_at = clock()
        self.finished_at = None
        self._clock = clock
        self._log = deque(maxlen=max_log_lines)
        self._lock = threading.Lock()

    @property
    def is_finished(self) -> bool:
        return self.phase in TERMINAL_PHASES

    def append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)

    def set_phase(self, phase: str, percent: Optional[float] = None) -> None:
        with self._lock:
            self.phase = phase
            if percent is not None:
                self.percent = percent

    def finish(self, phase: str, exit_code: Optional[int] = None,
               error: Optional[str] = None) -> None:
        with self._lock:
            self.phase = phase
            self.percent = 100
            self.exit_code = exit_code
            self.error = error
            self.finished_at = self._clock()

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "package": self.package,
                "action": self.action,
                "phase": self.phase,
                "percent": self.percent,
                "exit_code": self.exit_code,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "log": list(self._log),
            }


class JobRegistry:
    """Holds jobs and serialises operations.

    dpkg takes an exclusive lock anyway, so allowing concurrent installs would
    only produce a confusing apt error. Refusing up front gives a clean 409.
    """

    def __init__(self, max_log_lines: int = DEFAULT_MAX_LOG_LINES,
                 clock=time.time, id_factory=None):
        self._jobs = {}
        self._lock = threading.Lock()
        self._max_log_lines = max_log_lines
        self._clock = clock
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._active_id = None

    @property
    def active_job(self) -> Optional[Job]:
        with self._lock:
            return self._active()

    def _active(self) -> Optional[Job]:
        if self._active_id is None:
            return None
        job = self._jobs.get(self._active_id)
        if job is None or job.is_finished:
            return None
        return job

    def create(self, package: str, action: str) -> Job:
        with self._lock:
            active = self._active()
            if active is not None:
                raise ExtensionBusy(
                    f"{active.action} of {active.package} is already running"
                )
            job = Job(self._id_factory(), package, action,
                      self._clock, self._max_log_lines)
            self._jobs[job.id] = job
            self._active_id = job.id
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)
