import os
from configurator.memoryinfo import parse_cgroup_unit, ProcMemoryReader


def test_user_service_takes_leaf_not_user_at_service():
    text = "0::/user.slice/user-1001.slice/user@1001.service/session.slice/pipewire.service\n"
    unit, uid = parse_cgroup_unit(text)
    assert unit == "pipewire.service"
    assert uid == 1001


def test_app_slice_user_service():
    text = "0::/user.slice/user-1001.slice/user@1001.service/app.slice/mpd.service\n"
    assert parse_cgroup_unit(text) == ("mpd.service", 1001)


def test_system_service():
    assert parse_cgroup_unit("0::/system.slice/config-server.service\n") == ("config-server.service", None)


def test_templated_unit_is_kept_whole():
    assert parse_cgroup_unit("0::/system.slice/system-getty.slice/getty@tty1.service\n") == ("getty@tty1.service", None)


def test_scope_is_a_unit():
    text = "0::/user.slice/user-1001.slice/session-3.scope\n"
    assert parse_cgroup_unit(text) == ("session-3.scope", 1001)


def test_init_scope_under_user_manager_is_not_a_unit():
    text = "0::/user.slice/user-1001.slice/user@1001.service/init.scope\n"
    assert parse_cgroup_unit(text) == (None, 1001)


def test_kernel_thread_has_no_unit():
    assert parse_cgroup_unit("0::/\n") == (None, None)


def _mkproc(root, pid, ppid=1, comm="thing", cgroup="0::/system.slice/thing.service",
            rollup=None, cmdline="thing", statm=None):
    d = os.path.join(str(root), str(pid))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "comm"), "w") as f:
        f.write(comm + "\n")
    with open(os.path.join(d, "cgroup"), "w") as f:
        f.write(cgroup + "\n")
    with open(os.path.join(d, "cmdline"), "w") as f:
        f.write(cmdline)
    # /proc/PID/stat: pid (comm) state ppid ...
    with open(os.path.join(d, "stat"), "w") as f:
        f.write(f"{pid} ({comm}) S {ppid} 0 0 0 0 0 0 0 0 0 0\n")
    if rollup is not None:
        with open(os.path.join(d, "smaps_rollup"), "w") as f:
            f.write(rollup)
    if statm is not None:
        with open(os.path.join(d, "statm"), "w") as f:
            f.write(statm)
    return d


ROLLUP = """55c0f0000000-ffffffffff601000 ---p 00000000 00:00 0 [rollup]
Rss:               12000 kB
Pss:                8000 kB
Shared_Clean:       4000 kB
Shared_Dirty:          0 kB
Private_Clean:      1000 kB
Private_Dirty:      7000 kB
Swap:                600 kB
SwapPss:             500 kB
"""


def test_reads_a_process(tmp_path):
    _mkproc(tmp_path, 42, ppid=1, comm="mpd",
            cgroup="0::/user.slice/user-1001.slice/user@1001.service/app.slice/mpd.service",
            rollup=ROLLUP)
    procs = ProcMemoryReader(proc_root=str(tmp_path)).read_all()
    assert len(procs) == 1
    p = procs[0]
    assert (p.pid, p.ppid, p.comm, p.unit, p.uid) == (42, 1, "mpd", "mpd.service", 1001)
    assert (p.rss_kb, p.pss_kb, p.swap_pss_kb) == (12000, 8000, 500)
    assert p.private_kb == 8000       # Private_Clean + Private_Dirty
    assert p.shared_kb == 4000        # Shared_Clean + Shared_Dirty
    assert p.partial is False


def test_ignores_non_numeric_entries(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), "self"), exist_ok=True)
    _mkproc(tmp_path, 7, rollup=ROLLUP)
    assert [p.pid for p in ProcMemoryReader(proc_root=str(tmp_path)).read_all()] == [7]


def test_vanishing_pid_is_skipped(tmp_path):
    _mkproc(tmp_path, 8, rollup=ROLLUP)
    os.makedirs(os.path.join(str(tmp_path), "9"), exist_ok=True)  # no files: raced away
    assert [p.pid for p in ProcMemoryReader(proc_root=str(tmp_path)).read_all()] == [8]


def test_falls_back_to_statm_when_rollup_missing(tmp_path):
    # 3000 resident pages * 4 kB = 12000 kB
    _mkproc(tmp_path, 10, comm="old", rollup=None, statm="5000 3000 900 100 0 400 0\n")
    p = ProcMemoryReader(proc_root=str(tmp_path)).read_all()[0]
    assert p.rss_kb == 12000
    assert p.pss_kb is None
    assert p.partial is True


def test_kernel_thread_is_reported_with_no_unit(tmp_path):
    _mkproc(tmp_path, 2, comm="kthreadd", cgroup="0::/", cmdline="", statm="0 0 0 0 0 0 0\n")
    p = ProcMemoryReader(proc_root=str(tmp_path)).read_all()[0]
    assert p.comm == "kthreadd"
    assert p.unit is None
    assert p.rss_kb == 0
