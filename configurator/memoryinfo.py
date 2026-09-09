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

# What a *shipped* descriptor gets when it names units but omits the field.
# Someone wrote that file knowing the feature, so "disable" is a fair guess.
DEFAULT_DISPOSITION = "disable"

# What a *derived* feature gets -- a unit on the device that no descriptor
# claims. Nobody has classified it, and most of what lands here is core
# plumbing: dbus, systemd-journald, systemd-udevd, polkit, ssh. Offering to
# reduce those is worse than offering nothing, so they are reported without
# an action. Deliberately a separate constant from DEFAULT_DISPOSITION: the
# two cases look alike but mean opposite things.
DERIVED_DISPOSITION = "none"


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


DPKG_STATUS_PATH = "/var/lib/dpkg/status"


def dpkg_package_lookup(units: List[str]) -> dict:
    """Map unit name -> owning debian package, in two batched subprocess calls.

    The uncached lookup. Callers that run repeatedly should go through
    DpkgPackageResolver rather than calling this directly.
    """
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


class DpkgPackageResolver:
    """dpkg_package_lookup, memoised against the mtime of dpkg's status file.

    GET /memory is polled every 60 s per open tab, and `dpkg -S` over ~30 unit
    fragment paths on SD-card storage is not cheap. Nothing the answer depends
    on changes unless a package is installed or removed, and dpkg rewrites
    /var/lib/dpkg/status when that happens -- so its mtime is the invalidation
    signal, and a stale answer cannot outlive the change that made it stale.

    Deliberately an instance, not a module-level cache: MemoryInfo owns one
    for the life of the process (the handler is built once at server start),
    while every test gets a fresh one with nothing to reset.
    """

    def __init__(self, status_path: str = DPKG_STATUS_PATH, lookup=None):
        self.status_path = status_path
        self.lookup = lookup or dpkg_package_lookup
        self._stamp = None
        self._cache = {}

    def _stamp_now(self):
        try:
            stat = os.stat(self.status_path)
        except OSError:
            # No dpkg on this system, or the file is unreadable. Nothing can
            # invalidate the cache, and nothing it holds can go stale either.
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def __call__(self, units: List[str]) -> dict:
        if not units:
            return {}

        stamp = self._stamp_now()
        if stamp != self._stamp:
            self._cache = {}
            self._stamp = stamp

        missing = [u for u in units if u not in self._cache]
        if missing:
            found = self.lookup(missing)
            # Remember the misses as well. Most units on a device belong to no
            # package dpkg can name -- re-asking about those on every poll is
            # the bulk of the cost this cache exists to avoid.
            for unit in missing:
                self._cache[unit] = found.get(unit)

        return {u: self._cache[u] for u in units if self._cache.get(u) is not None}


_BUCKETS = {
    "kernel": ("Kernel", "none"),
    "system": ("System", "none"),
    "user-session": ("User session", "none"),
}


class FeatureResolver:
    """Assigns every process to exactly one feature."""

    def __init__(self, descriptors: List[FeatureDescriptor], package_resolver=None):
        self.descriptors = descriptors
        # Uncached: a FeatureResolver is built fresh for every collect(), so a
        # per-instance cache here would never be reused. MemoryInfo passes its
        # own long-lived DpkgPackageResolver in.
        self.package_resolver = package_resolver or dpkg_package_lookup
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
                    disposition=DERIVED_DISPOSITION,
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


def parse_meminfo(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(':')
        fields = rest.split()
        if not fields:
            continue
        try:
            values[key.strip()] = int(fields[0])
        except ValueError:
            continue
    return values


def systemd_state_resolver(units: List[str]) -> dict:
    """Map unit -> ActiveState via the existing manager, system and user units alike."""
    if not units:
        return {}
    try:
        from .systemd_service import SystemdServiceManager
        manager = SystemdServiceManager()
    except Exception as e:
        logger.warning("Cannot query unit state: %s", e)
        return {}

    # list_services() returns every unit in one pass, system and user alike.
    # status() would cost three subprocess calls per unit.
    try:
        ok, services = manager.list_services()
    except Exception as e:
        logger.warning("Cannot list units: %s", e)
        return {}

    active = {s['name']: s.get('active') for s in services} if ok else {}
    return {unit: active.get(unit) for unit in units}


class MemoryInfo:
    """Collects a full memory report: system totals plus per-feature usage."""

    def __init__(self, proc_root: str = "/proc",
                 features_d_dirs: Optional[List[str]] = None,
                 players_d_dirs: Optional[List[str]] = None,
                 package_resolver=None, state_resolver=None,
                 meminfo_path: str = "/proc/meminfo"):
        self.proc_root = proc_root
        self.features_d_dirs = FEATURES_D_DIRS if features_d_dirs is None else features_d_dirs
        self.players_d_dirs = PLAYERS_D_DIRS if players_d_dirs is None else players_d_dirs
        self.package_resolver = package_resolver or DpkgPackageResolver()
        self.state_resolver = state_resolver or systemd_state_resolver
        self.meminfo_path = meminfo_path

    def _descriptors(self) -> List[FeatureDescriptor]:
        # players.d first so an explicit features.d entry can override a player.
        descriptors = {d.id: d for d in descriptors_from_players(self.players_d_dirs)}
        for descriptor in load_descriptors(self.features_d_dirs):
            descriptors[descriptor.id] = descriptor
        return list(descriptors.values())

    def _system(self, meminfo: dict, total_pss_kb: int) -> dict:
        total = meminfo.get('MemTotal', 0)
        free = meminfo.get('MemFree', 0)
        cached = meminfo.get('Cached', 0)
        buffers = meminfo.get('Buffers', 0)
        swap_total = meminfo.get('SwapTotal', 0)
        swap_free = meminfo.get('SwapFree', 0)

        # Shared memory is counted both in Cached and in process PSS, so this
        # can go slightly negative on a busy device. Report the floor.
        unaccounted = total - total_pss_kb - cached - buffers - free

        return {
            'total_kb': total,
            'free_kb': free,
            'available_kb': meminfo.get('MemAvailable', 0),
            'used_kb': total - meminfo.get('MemAvailable', 0),
            'cached_kb': cached,
            'buffers_kb': buffers,
            'swap_total_kb': swap_total,
            'swap_used_kb': swap_total - swap_free,
            'process_pss_kb': total_pss_kb,
            'unaccounted_kb': max(unaccounted, 0),
        }

    def collect(self, include_processes: bool = False) -> dict:
        processes = ProcMemoryReader(self.proc_root).read_all()
        resolver = FeatureResolver(self._descriptors(), package_resolver=self.package_resolver)
        groups = resolver.resolve(processes)

        units = sorted({u for feature_id in groups
                        for u in resolver.describe(feature_id).units})
        states = self.state_resolver(units)

        features = []
        total_pss = 0
        for feature_id, members in groups.items():
            descriptor = resolver.describe(feature_id)
            rss = sum(p.rss_kb for p in members)
            pss = sum((p.pss_kb or 0) for p in members)
            private = sum(p.private_kb for p in members)
            shared = sum(p.shared_kb for p in members)
            swap = sum(p.swap_kb for p in members)
            swap_pss = sum(p.swap_pss_kb for p in members)
            total_pss += pss

            row = {
                'id': feature_id,
                'name': descriptor.name,
                'category': descriptor.category,
                'icon': descriptor.icon,
                'package': descriptor.provided_by,
                'units': descriptor.units,
                'state': next((states.get(u) for u in descriptor.units
                               if states.get(u)), None),
                'processes': len(members),
                'disposition': descriptor.disposition,
                'partial': any(p.partial for p in members),
                'memory': {
                    'rss_kb': rss,
                    'pss_kb': pss,
                    'private_kb': private,
                    'shared_kb': shared,
                    'swap_kb': swap,
                    'swap_pss_kb': swap_pss,
                    'reclaimable': {
                        'min_kb': private + swap_pss,
                        'estimate_kb': pss + swap_pss,
                    },
                },
            }
            if include_processes:
                row['process_list'] = [
                    {'pid': p.pid, 'comm': p.comm, 'rss_kb': p.rss_kb,
                     'pss_kb': p.pss_kb, 'private_kb': p.private_kb,
                     'swap_pss_kb': p.swap_pss_kb}
                    for p in sorted(members, key=lambda x: x.rss_kb, reverse=True)
                ]
            features.append(row)

        features.sort(key=lambda f: f['memory']['reclaimable']['estimate_kb'], reverse=True)

        try:
            with open(self.meminfo_path, 'r') as f:
                meminfo = parse_meminfo(f.read())
        except OSError as e:
            logger.error("Cannot read %s: %s", self.meminfo_path, e)
            meminfo = {}

        return {'system': self._system(meminfo, total_pss), 'features': features}
