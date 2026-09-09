#!/usr/bin/env python3
"""
Per-process memory collection.

Reads /proc and reports one record per process. Feature attribution lives in
the resolver; this module only knows about processes and their owning unit.
"""

import glob
import json
import logging
import os
import re
import subprocess
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


FEATURES_D_DIRS = ["/usr/share/hifiberry/features.d", "/etc/hifiberry/features.d"]
PLAYERS_D_DIRS = ["/usr/share/hifiberry/players.d", "/etc/hifiberry/players.d"]

VALID_DISPOSITIONS = ("required", "disable", "uninstall", "reconfigure", "none")
DEFAULT_DISPOSITION = "disable"


@dataclass
class FeatureDescriptor:
    id: str
    name: str
    provided_by: Optional[str]
    units: List[str]
    processes: List[str]
    icon: Optional[str]
    category: Optional[str]
    disposition: str


def _descriptor_from_dict(feature_id: str, data: dict) -> Optional[FeatureDescriptor]:
    units = data.get("systemd_services") or []
    processes = data.get("processes") or []
    if not units and not processes:
        logger.warning("features.d/%s claims neither units nor processes, skipping", feature_id)
        return None

    disposition = data.get("disposition", DEFAULT_DISPOSITION)
    if disposition not in VALID_DISPOSITIONS:
        logger.warning("features.d/%s has unknown disposition %r, using %s",
                       feature_id, disposition, DEFAULT_DISPOSITION)
        disposition = DEFAULT_DISPOSITION

    return FeatureDescriptor(
        id=feature_id,
        name=data.get("name", feature_id),
        provided_by=data.get("provided_by"),
        units=[u if u.endswith(_UNIT_SUFFIXES) else u + ".service" for u in units],
        processes=list(processes),
        icon=data.get("icon"),
        category=data.get("category"),
        disposition=disposition,
    )


def load_descriptors(dirs: List[str]) -> List[FeatureDescriptor]:
    """Load features.d descriptors. Later directories override earlier ones by id."""
    by_id = {}
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            feature_id = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                logger.warning("Ignoring invalid descriptor %s: %s", path, e)
                continue
            descriptor = _descriptor_from_dict(feature_id, data)
            if descriptor is not None:
                by_id[feature_id] = descriptor
    return list(by_id.values())


def descriptors_from_players(dirs: List[str]) -> List[FeatureDescriptor]:
    """Reuse the existing players.d registry so every player is already named."""
    by_id = {}
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            feature_id = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                logger.warning("Ignoring invalid player descriptor %s: %s", path, e)
                continue
            service = data.get("systemd_service")
            if not service:
                continue
            by_id[feature_id] = FeatureDescriptor(
                id=feature_id,
                name=data.get("name", feature_id),
                provided_by=data.get("provided_by"),
                units=[service if service.endswith(_UNIT_SUFFIXES) else service + ".service"],
                processes=[],
                icon=data.get("icon"),
                category="player",
                # Players are extensions: the extensions page removes them.
                disposition="uninstall",
            )
    return list(by_id.values())


def dpkg_package_resolver(units: List[str]) -> dict:
    """Map unit name -> owning debian package, in two batched subprocess calls."""
    if not units:
        return {}

    paths = {}
    try:
        show = subprocess.run(
            ["systemctl", "show", "--property=Id", "--property=FragmentPath"] + units,
            capture_output=True, text=True, check=False, timeout=10,
        )
        unit_id = None
        for line in show.stdout.splitlines():
            if line.startswith("Id="):
                unit_id = line[3:].strip()
            elif line.startswith("FragmentPath="):
                fragment = line[len("FragmentPath="):].strip()
                if unit_id and fragment:
                    paths[fragment] = unit_id
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("systemctl show failed, unit names will not resolve to packages: %s", e)
        return {}

    if not paths:
        return {}

    packages = {}
    try:
        search = subprocess.run(
            ["dpkg", "-S"] + list(paths),
            capture_output=True, text=True, check=False, timeout=10,
        )
        for line in search.stdout.splitlines():
            package, _, path = line.partition(": ")
            path = path.strip()
            if path in paths:
                # dpkg lists co-owners comma-separated; the first is enough.
                packages[paths[path]] = package.split(',')[0].strip()
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("dpkg -S failed, unit names will not resolve to packages: %s", e)

    return packages


_BUCKETS = {
    "kernel": ("Kernel", "none"),
    "system": ("System", "none"),
    "user-session": ("User session", "none"),
}


class FeatureResolver:
    """Assigns every process to exactly one feature."""

    def __init__(self, descriptors: List[FeatureDescriptor], package_resolver=None):
        self.descriptors = descriptors
        self.package_resolver = package_resolver or dpkg_package_resolver
        self._by_id = {d.id: d for d in descriptors}
        self._by_unit = {}
        for descriptor in descriptors:
            for unit in descriptor.units:
                self._by_unit[unit] = descriptor
        self._process_claims = {}
        for descriptor in descriptors:
            for comm in descriptor.processes:
                self._process_claims[comm] = descriptor

    def describe(self, feature_id: str) -> FeatureDescriptor:
        return self._by_id[feature_id]

    def _register(self, descriptor: FeatureDescriptor):
        self._by_id.setdefault(descriptor.id, descriptor)

    def resolve(self, processes: List[ProcessMemory]) -> dict:
        by_pid = {p.pid: p for p in processes}
        children = {}
        for p in processes:
            children.setdefault(p.ppid, []).append(p.pid)

        assigned = {}

        # 1. Subtree claims first. A named process and everything below it wins
        #    over the generic unit it happens to sit in (getty@tty1.service).
        for p in processes:
            descriptor = self._process_claims.get(p.comm)
            if descriptor is None or p.pid in assigned:
                continue
            stack = [p.pid]
            while stack:
                pid = stack.pop()
                if pid in assigned:
                    continue
                assigned[pid] = descriptor.id
                stack.extend(children.get(pid, []))

        # 2. Unit claims for whatever is left.
        undecided = [p for p in processes if p.pid not in assigned]
        derived_units = sorted({p.unit for p in undecided
                                if p.unit and p.unit not in self._by_unit})
        packages = self.package_resolver(derived_units) if derived_units else {}

        for p in undecided:
            if p.unit and p.unit in self._by_unit:
                assigned[p.pid] = self._by_unit[p.unit].id
                continue
            if p.unit:
                feature_id = p.unit.rsplit('.', 1)[0]
                self._register(FeatureDescriptor(
                    id=feature_id, name=feature_id,
                    provided_by=packages.get(p.unit),
                    units=[p.unit], processes=[], icon=None, category=None,
                    disposition=DEFAULT_DISPOSITION,
                ))
                assigned[p.pid] = feature_id
                continue

            # 3. No unit at all.
            if p.pss_kb is None and p.rss_kb == 0:
                bucket = "kernel"
            elif p.uid is not None:
                bucket = "user-session"
            else:
                bucket = "system"
            name, disposition = _BUCKETS[bucket]
            self._register(FeatureDescriptor(
                id=bucket, name=name, provided_by=None, units=[], processes=[],
                icon=None, category=None, disposition=disposition,
            ))
            assigned[p.pid] = bucket

        groups = {}
        for pid, feature_id in assigned.items():
            groups.setdefault(feature_id, []).append(by_pid[pid])
        return groups
