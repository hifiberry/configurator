import json
import os
from configurator.memoryinfo import MemoryInfo

MEMINFO = """MemTotal:        2027104 kB
MemFree:          400000 kB
MemAvailable:     812340 kB
Buffers:           18200 kB
Cached:           210400 kB
SwapTotal:        102396 kB
SwapFree:          98300 kB
"""

ROLLUP = """55c0-ffff ---p 0 00:00 0 [rollup]
Rss:               12000 kB
Pss:                8000 kB
Shared_Clean:       4000 kB
Shared_Dirty:          0 kB
Private_Clean:      1000 kB
Private_Dirty:      7000 kB
Swap:                600 kB
SwapPss:             500 kB
"""


def _mkproc(root, pid, comm, unit, ppid=1):
    d = os.path.join(str(root), str(pid))
    os.makedirs(d, exist_ok=True)
    for name, content in (("comm", comm + "\n"),
                          ("cgroup", "0::/system.slice/%s\n" % unit),
                          ("cmdline", comm),
                          ("stat", "%d (%s) S %d 0 0 0\n" % (pid, comm, ppid)),
                          ("smaps_rollup", ROLLUP)):
        with open(os.path.join(d, name), "w") as f:
            f.write(content)


def _fixture(tmp_path):
    proc = tmp_path / "proc"
    features_d = tmp_path / "features.d"
    os.makedirs(str(features_d), exist_ok=True)
    with open(os.path.join(str(features_d), "mpd.json"), "w") as f:
        json.dump({"name": "Music Player Daemon", "provided_by": "hifiberry-mpd",
                   "systemd_services": ["mpd.service"], "disposition": "disable"}, f)
    with open(os.path.join(str(features_d), "audiocontrol.json"), "w") as f:
        json.dump({"name": "Audio control", "provided_by": "hifiberry-audiocontrol",
                   "systemd_services": ["audiocontrol.service"],
                   "disposition": "required"}, f)
    meminfo = tmp_path / "meminfo"
    with open(str(meminfo), "w") as f:
        f.write(MEMINFO)
    _mkproc(proc, 10, "mpd", "mpd.service")
    _mkproc(proc, 11, "audiocontrol", "audiocontrol.service")
    return MemoryInfo(
        proc_root=str(proc),
        features_d_dirs=[str(features_d)],
        players_d_dirs=[],
        package_resolver=lambda units: {},
        state_resolver=lambda units: {u: "running" for u in units},
        meminfo_path=str(meminfo),
    )


def test_system_totals(tmp_path):
    result = _fixture(tmp_path).collect()
    assert result["system"]["total_kb"] == 2027104
    assert result["system"]["available_kb"] == 812340
    assert result["system"]["swap_total_kb"] == 102396
    assert result["system"]["swap_used_kb"] == 102396 - 98300


def test_feature_rows_carry_names_and_disposition(tmp_path):
    result = _fixture(tmp_path).collect()
    rows = {f["id"]: f for f in result["features"]}
    assert rows["mpd"]["name"] == "Music Player Daemon"
    assert rows["mpd"]["disposition"] == "disable"
    assert rows["mpd"]["package"] == "hifiberry-mpd"
    assert rows["audiocontrol"]["disposition"] == "required"


def test_memory_numbers_are_summed_per_feature(tmp_path):
    result = _fixture(tmp_path).collect()
    mpd = [f for f in result["features"] if f["id"] == "mpd"][0]
    assert mpd["memory"]["rss_kb"] == 12000
    assert mpd["memory"]["pss_kb"] == 8000
    assert mpd["memory"]["private_kb"] == 8000
    assert mpd["memory"]["shared_kb"] == 4000
    assert mpd["memory"]["swap_pss_kb"] == 500
    # floor = private + swap_pss; estimate = pss + swap_pss
    assert mpd["memory"]["reclaimable"] == {"min_kb": 8500, "estimate_kb": 8500}


def test_features_are_sorted_by_reclaimable_estimate(tmp_path):
    result = _fixture(tmp_path).collect()
    estimates = [f["memory"]["reclaimable"]["estimate_kb"] for f in result["features"]]
    assert estimates == sorted(estimates, reverse=True)


def test_unaccounted_is_reported_and_never_negative(tmp_path):
    result = _fixture(tmp_path).collect()
    assert result["system"]["unaccounted_kb"] >= 0


def test_processes_are_omitted_by_default(tmp_path):
    result = _fixture(tmp_path).collect()
    assert "process_list" not in result["features"][0]


def test_processes_are_included_on_request(tmp_path):
    result = _fixture(tmp_path).collect(include_processes=True)
    mpd = [f for f in result["features"] if f["id"] == "mpd"][0]
    assert mpd["process_list"][0]["pid"] == 10
    assert mpd["process_list"][0]["comm"] == "mpd"


def test_unit_state_comes_from_the_state_resolver(tmp_path):
    result = _fixture(tmp_path).collect()
    assert all(f["state"] in ("running", None) for f in result["features"])


# --- The statm fallback, end to end. A kernel thread has no mm, so it has no
# smaps_rollup at all and the reader falls back to statm, which only reports
# RSS -- and for a kernel thread that is zero too. This is the path that
# produces the "Kernel" row, and until now only the reader saw it: nothing
# drove it through collect() to see what the aggregate actually looks like.

def _mkproc_without_rollup(root, pid, comm, ppid=0, resident_pages=0):
    """A process the way the kernel presents a kernel thread: cgroup root, no
    smaps_rollup, statm present."""
    d = os.path.join(str(root), str(pid))
    os.makedirs(d, exist_ok=True)
    for name, content in (("comm", comm + "\n"),
                          ("cgroup", "0::/\n"),
                          ("cmdline", ""),
                          ("stat", "%d (%s) S %d 0 0 0\n" % (pid, comm, ppid)),
                          ("statm", "0 %d 0 0 0 0 0\n" % resident_pages)):
        with open(os.path.join(d, name), "w") as f:
            f.write(content)


def _kernel_thread_fixture(tmp_path):
    proc = tmp_path / "proc"
    meminfo = tmp_path / "meminfo"
    with open(str(meminfo), "w") as f:
        f.write(MEMINFO)
    _mkproc(proc, 10, "mpd", "mpd.service")
    _mkproc_without_rollup(proc, 2, "kthreadd")
    _mkproc_without_rollup(proc, 3, "ksoftirqd/0", ppid=2)
    return MemoryInfo(
        proc_root=str(proc),
        features_d_dirs=[],
        players_d_dirs=[],
        package_resolver=lambda units: {},
        state_resolver=lambda units: {},
        meminfo_path=str(meminfo),
    )


def _kernel_row(tmp_path):
    result = _kernel_thread_fixture(tmp_path).collect()
    return [f for f in result["features"] if f["id"] == "kernel"][0]


def test_a_process_without_smaps_rollup_flags_its_feature_partial(tmp_path):
    assert _kernel_row(tmp_path)["partial"] is True


def test_pss_of_processes_without_smaps_rollup_aggregates_to_zero(tmp_path):
    """pss_kb is None for every member, so the sum is 0 -- not a missing
    figure but a real one: PSS of a kernel thread is zero by definition."""
    row = _kernel_row(tmp_path)
    assert row["processes"] == 2
    assert row["memory"]["pss_kb"] == 0
    assert row["memory"]["rss_kb"] == 0
    assert row["memory"]["reclaimable"] == {"min_kb": 0, "estimate_kb": 0}
