import json
import os
from configurator.memoryinfo import (
    ProcessMemory, FeatureResolver, FeatureDescriptor,
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
