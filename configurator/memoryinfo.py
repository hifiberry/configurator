#!/usr/bin/env python3
"""
Per-process memory collection.

Reads /proc and reports one record per process. Feature attribution lives in
the resolver; this module only knows about processes and their owning unit.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# systemd puts a user manager's own tree under user@<uid>.service. That is a
# container for the user's units, not a unit anyone would want reported, and
# neither is the manager's init.scope. The unit is the leaf below them --
# a cgroup path legitimately holds more than one ".service" component.
_CONTAINER_RE = re.compile(r'^(user@\d+\.service|init\.scope)$')
_USER_SLICE_RE = re.compile(r'^user-(\d+)\.slice$')
_UNIT_SUFFIXES = ('.service', '.scope')

PAGE_SIZE_KB = 4


def parse_cgroup_unit(text: str) -> Tuple[Optional[str], Optional[int]]:
    """Return (unit, uid) for the contents of /proc/PID/cgroup.

    cgroup v2 writes a single "0::<path>" line. The unit is the last path
    component ending in .service or .scope, skipping systemd's own containers.
    """
    unit = None
    uid = None

    for line in text.splitlines():
        parts = line.split(':', 2)
        if len(parts) != 3:
            continue
        path = parts[2]

        components = [c for c in path.split('/') if c]
        for component in components:
            match = _USER_SLICE_RE.match(component)
            if match:
                uid = int(match.group(1))

        for component in reversed(components):
            if _CONTAINER_RE.match(component):
                continue
            if component.endswith(_UNIT_SUFFIXES):
                unit = component
                break
        if unit:
            break

    return unit, uid


@dataclass
class ProcessMemory:
    pid: int
    ppid: int
    comm: str
    unit: Optional[str]
    uid: Optional[int]
    rss_kb: int
    pss_kb: Optional[int]
    private_kb: int
    shared_kb: int
    swap_kb: int
    swap_pss_kb: int
    partial: bool


def _parse_rollup(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, _, rest = line.partition(':')
        fields = rest.split()
        if not fields:
            continue
        try:
            values[key.strip()] = int(fields[0])
        except ValueError:
            continue
    return values


class ProcMemoryReader:
    """Walks /proc and returns one ProcessMemory per live process."""

    def __init__(self, proc_root: str = "/proc"):
        self.proc_root = proc_root

    def _read(self, pid_dir: str, name: str) -> str:
        with open(os.path.join(pid_dir, name), 'r') as f:
            return f.read()

    def read_all(self) -> List[ProcessMemory]:
        processes = []
        try:
            entries = os.listdir(self.proc_root)
        except OSError as e:
            logger.error("Cannot list %s: %s", self.proc_root, e)
            return processes

        for entry in entries:
            if not entry.isdigit():
                continue
            proc = self._read_one(os.path.join(self.proc_root, entry), int(entry))
            if proc is not None:
                processes.append(proc)
        return processes

    def _read_one(self, pid_dir: str, pid: int) -> Optional[ProcessMemory]:
        try:
            comm = self._read(pid_dir, 'comm').strip()
            stat = self._read(pid_dir, 'stat')
            unit, uid = parse_cgroup_unit(self._read(pid_dir, 'cgroup'))
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            # The process exited between listdir and read, or is not ours.
            return None

        # /proc/PID/stat: "pid (comm) state ppid ...". comm may contain spaces
        # and parentheses, so split after the last ')'.
        try:
            ppid = int(stat[stat.rindex(')') + 1:].split()[1])
        except (ValueError, IndexError):
            ppid = 0

        partial = False
        try:
            rollup = _parse_rollup(self._read(pid_dir, 'smaps_rollup'))
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            rollup = {}

        if rollup:
            rss = rollup.get('Rss', 0)
            pss = rollup.get('Pss')
            private = rollup.get('Private_Clean', 0) + rollup.get('Private_Dirty', 0)
            shared = rollup.get('Shared_Clean', 0) + rollup.get('Shared_Dirty', 0)
            swap = rollup.get('Swap', 0)
            swap_pss = rollup.get('SwapPss', 0)
        else:
            # Kernel threads have no rollup at all; very old kernels lack the
            # file. Fall back to statm, which only gives RSS.
            partial = True
            rss = 0
            try:
                fields = self._read(pid_dir, 'statm').split()
                rss = int(fields[1]) * PAGE_SIZE_KB
            except (FileNotFoundError, ProcessLookupError, PermissionError,
                    OSError, IndexError, ValueError):
                pass
            pss = None
            private = rss
            shared = 0
            swap = 0
            swap_pss = 0

        return ProcessMemory(
            pid=pid, ppid=ppid, comm=comm, unit=unit, uid=uid,
            rss_kb=rss, pss_kb=pss, private_kb=private, shared_kb=shared,
            swap_kb=swap, swap_pss_kb=swap_pss, partial=partial,
        )
