import json
import os
from configurator.memoryinfo import (
    ProcessMemory, FeatureResolver, FeatureDescriptor, DpkgPackageResolver,
    load_descriptors, descriptors_from_players,
)


def _proc(pid, comm, unit=None, ppid=1):
    return ProcessMemory(pid=pid, ppid=ppid, comm=comm, unit=unit, uid=None,
                         rss_kb=1000, pss_kb=800, private_kb=700, shared_kb=300,
                         swap_kb=0, swap_pss_kb=0, partial=False)


def _write(dir_path, filename, payload):
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), "w") as f:
        json.dump(payload, f)


def test_loads_a_descriptor(tmp_path):
    _write(str(tmp_path), "mpd.json", {
        "name": "Music Player Daemon",
        "provided_by": "hifiberry-mpd",
        "systemd_services": ["mpd.service"],
        "disposition": "disable",
    })
    descriptors = load_descriptors([str(tmp_path)])
    assert len(descriptors) == 1
    assert descriptors[0].id == "mpd"
    assert descriptors[0].name == "Music Player Daemon"
    assert descriptors[0].units == ["mpd.service"]
    assert descriptors[0].disposition == "disable"


def test_etc_overrides_usr(tmp_path):
    usr = tmp_path / "usr"
    etc = tmp_path / "etc"
    _write(str(usr), "mpd.json", {"name": "Vendor", "systemd_services": ["mpd.service"]})
    _write(str(etc), "mpd.json", {"name": "Local", "systemd_services": ["mpd.service"]})
    descriptors = load_descriptors([str(usr), str(etc)])
    assert [d.name for d in descriptors] == ["Local"]


def test_invalid_json_is_skipped_not_fatal(tmp_path):
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(os.path.join(str(tmp_path), "broken.json"), "w") as f:
        f.write("{not json")
    _write(str(tmp_path), "ok.json", {"name": "Fine", "systemd_services": ["a.service"]})
    assert [d.name for d in load_descriptors([str(tmp_path)])] == ["Fine"]


def test_descriptor_with_neither_units_nor_processes_is_skipped(tmp_path):
    _write(str(tmp_path), "empty.json", {"name": "Nothing"})
    assert load_descriptors([str(tmp_path)]) == []


def test_unknown_disposition_falls_back_to_disable(tmp_path):
    _write(str(tmp_path), "x.json", {"name": "X", "systemd_services": ["x.service"],
                                     "disposition": "explode"})
    assert load_descriptors([str(tmp_path)])[0].disposition == "disable"


def test_descriptor_omitting_disposition_defaults_to_disable(tmp_path):
    """A shipped descriptor is written by someone who knows the feature. If it
    names units but leaves the disposition out, "disable" is the right guess.
    That default is deliberately *not* the one used for derived features --
    see test_derived_features_are_not_offered_as_reducible."""
    _write(str(tmp_path), "y.json", {"name": "Y", "systemd_services": ["y.service"]})
    assert load_descriptors([str(tmp_path)])[0].disposition == "disable"


def test_players_d_descriptors_are_reused(tmp_path):
    _write(str(tmp_path), "shairport.json", {
        "name": "AirPlay",
        "provided_by": "hifiberry-shairport",
        "systemd_service": "shairport",
        "icon": "airplay",
    })
    descriptors = descriptors_from_players([str(tmp_path)])
    assert descriptors[0].name == "AirPlay"
    assert descriptors[0].units == ["shairport.service"]
    assert descriptors[0].icon == "airplay"
    assert descriptors[0].disposition == "uninstall"


def test_resolves_by_unit():
    d = FeatureDescriptor(id="mpd", name="MPD", provided_by=None,
                          units=["mpd.service"], processes=[], icon=None,
                          category=None, disposition="disable")
    resolver = FeatureResolver([d], package_resolver=lambda units: {})
    groups = resolver.resolve([_proc(1, "mpd", unit="mpd.service")])
    assert list(groups) == ["mpd"]


def test_subtree_claim_beats_the_generic_unit():
    # cog runs inside getty@tty1.service; the browser must not be filed there.
    d = FeatureDescriptor(id="display", name="Local display", provided_by=None,
                          units=[], processes=["cage", "cog"], icon=None,
                          category=None, disposition="reconfigure")
    procs = [
        _proc(100, "bash", unit="getty@tty1.service", ppid=1),
        _proc(101, "cage", unit="getty@tty1.service", ppid=100),
        _proc(102, "cog", unit="getty@tty1.service", ppid=101),
        _proc(103, "WebKitWebProces", unit="getty@tty1.service", ppid=102),
    ]
    resolver = FeatureResolver([d], package_resolver=lambda units: {})
    groups = resolver.resolve(procs)
    assert sorted(p.pid for p in groups["display"]) == [101, 102, 103]
    assert [p.pid for p in groups["getty@tty1"]] == [100]


def test_derived_feature_uses_package_name_when_known():
    resolver = FeatureResolver([], package_resolver=lambda units: {"tailscaled.service": "tailscale"})
    groups = resolver.resolve([_proc(5, "tailscaled", unit="tailscaled.service")])
    assert list(groups) == ["tailscaled"]
    assert resolver.describe("tailscaled").provided_by == "tailscale"
    assert resolver.describe("tailscaled").name == "tailscaled"


def test_derived_features_are_not_offered_as_reducible():
    """A unit with no shipped descriptor is one nobody has classified. Most of
    what lands here is core plumbing -- dbus, systemd-journald, systemd-udevd,
    polkit, ssh -- and telling an owner to reduce dbus to save RAM is worse
    than showing nothing. "none" means "reported, no action offered"."""
    resolver = FeatureResolver([], package_resolver=lambda units: {})
    resolver.resolve([_proc(7, "dbus-daemon", unit="dbus.service")])
    assert resolver.describe("dbus").disposition == "none"


def test_processes_without_a_unit_land_in_buckets():
    resolver = FeatureResolver([], package_resolver=lambda units: {})
    kernel = ProcessMemory(pid=2, ppid=0, comm="kthreadd", unit=None, uid=None,
                           rss_kb=0, pss_kb=None, private_kb=0, shared_kb=0,
                           swap_kb=0, swap_pss_kb=0, partial=True)
    user = _proc(900, "bash", unit=None)
    user.uid = 1001
    groups = resolver.resolve([kernel, user])
    assert "kernel" in groups
    assert "user-session" in groups
    assert resolver.describe("kernel").disposition == "none"


def test_each_process_lands_in_exactly_one_feature():
    d = FeatureDescriptor(id="display", name="Local display", provided_by=None,
                          units=["getty@tty1.service"], processes=["cog"], icon=None,
                          category=None, disposition="reconfigure")
    procs = [_proc(1, "cog", unit="getty@tty1.service")]
    groups = FeatureResolver([d], package_resolver=lambda units: {}).resolve(procs)
    assert sum(len(v) for v in groups.values()) == 1


# --- The dpkg lookup cache. GET /memory is polled every 60s per open tab and
# `dpkg -S` over ~30 unit fragment paths on SD-card storage is not cheap. The
# answer only changes when a package is installed or removed, and dpkg
# rewrites /var/lib/dpkg/status when that happens -- so its mtime is the
# invalidation signal.

def _status_file(tmp_path, mtime):
    path = tmp_path / "status"
    with open(str(path), "w") as f:
        f.write("Package: tailscale\n")
    os.utime(str(path), (mtime, mtime))
    return str(path)


def _recording_lookup(result):
    calls = []

    def lookup(units):
        calls.append(sorted(units))
        return {u: result[u] for u in units if u in result}

    return lookup, calls


def test_dpkg_lookup_is_not_repeated_while_dpkg_status_is_unchanged(tmp_path):
    status = _status_file(tmp_path, 1000)
    lookup, calls = _recording_lookup({"tailscaled.service": "tailscale"})
    resolver = DpkgPackageResolver(status_path=status, lookup=lookup)

    assert resolver(["tailscaled.service"]) == {"tailscaled.service": "tailscale"}
    assert resolver(["tailscaled.service"]) == {"tailscaled.service": "tailscale"}
    assert calls == [["tailscaled.service"]]


def test_dpkg_lookup_runs_again_once_dpkg_status_changes(tmp_path):
    status = _status_file(tmp_path, 1000)
    lookup, calls = _recording_lookup({"tailscaled.service": "tailscale"})
    resolver = DpkgPackageResolver(status_path=status, lookup=lookup)

    resolver(["tailscaled.service"])
    os.utime(status, (2000, 2000))          # a package was installed or removed
    resolver(["tailscaled.service"])
    assert calls == [["tailscaled.service"], ["tailscaled.service"]]


def test_dpkg_lookup_only_asks_about_units_it_has_not_seen(tmp_path):
    status = _status_file(tmp_path, 1000)
    lookup, calls = _recording_lookup({"a.service": "pkg-a", "b.service": "pkg-b"})
    resolver = DpkgPackageResolver(status_path=status, lookup=lookup)

    resolver(["a.service"])
    assert resolver(["a.service", "b.service"]) == {"a.service": "pkg-a", "b.service": "pkg-b"}
    assert calls == [["a.service"], ["b.service"]]


def test_a_unit_that_belongs_to_no_package_is_not_asked_about_again(tmp_path):
    """Most derived units on a device belong to no package dpkg can name.
    Re-asking about those every 60s is the whole cost this cache exists to
    avoid, so the misses are remembered too."""
    status = _status_file(tmp_path, 1000)
    lookup, calls = _recording_lookup({})
    resolver = DpkgPackageResolver(status_path=status, lookup=lookup)

    assert resolver(["mystery.service"]) == {}
    assert resolver(["mystery.service"]) == {}
    assert calls == [["mystery.service"]]


def test_dpkg_resolver_works_when_there_is_no_dpkg_status_file(tmp_path):
    lookup, calls = _recording_lookup({"a.service": "pkg-a"})
    resolver = DpkgPackageResolver(status_path=str(tmp_path / "absent"), lookup=lookup)
    assert resolver(["a.service"]) == {"a.service": "pkg-a"}


def test_empty_unit_list_does_not_shell_out(tmp_path):
    status = _status_file(tmp_path, 1000)
    lookup, calls = _recording_lookup({})
    assert DpkgPackageResolver(status_path=status, lookup=lookup)([]) == {}
    assert calls == []
