import subprocess
from unittest.mock import patch

from configurator import supportinfo


def _completed(stdout):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _failed(stderr, stdout=""):
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout=stdout, stderr=stderr
    )


def test_run_returns_stripped_stdout():
    with patch("subprocess.run", return_value=_completed("hello\n")):
        assert supportinfo._run(["true"]) == "hello"


def test_run_reports_missing_binary_instead_of_raising():
    with patch("subprocess.run", side_effect=FileNotFoundError("no journalctl")):
        result = supportinfo._run(["journalctl"])
    assert result.startswith("(command failed:")
    assert "no journalctl" in result


def test_run_reports_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
        assert supportinfo._run(["x"]).startswith("(command failed:")


def test_run_surfaces_stderr_when_stdout_is_empty_and_exit_is_nonzero():
    stderr = "Failed to determine journal file ownership: Permission denied"
    with patch("subprocess.run", return_value=_failed(stderr)):
        result = supportinfo._run(["journalctl"])
    assert result.startswith("(command failed:")
    assert stderr in result


def test_run_prefers_stdout_over_stderr_when_both_present():
    with patch(
        "subprocess.run",
        return_value=_failed("some warning on stderr", stdout="hifiberry-mpd 1.2.3\n"),
    ):
        assert supportinfo._run(["dpkg-query"]) == "hifiberry-mpd 1.2.3"


def test_collect_packages_asks_dpkg_for_the_known_patterns():
    with patch("subprocess.run", return_value=_completed("hifiberry-configurator 2.15.0\n")) as run:
        result = supportinfo.collect_packages()
    assert result == "hifiberry-configurator 2.15.0"
    cmd = run.call_args[0][0]
    assert cmd[0] == "dpkg-query"
    assert "hifiberry-*" in cmd
    assert "mpd" in cmd


def test_collect_journal_requests_a_wider_window_than_it_displays():
    # journalctl is asked for far more lines than `lines` requests (10x,
    # floor 200), so a flapping unit's repeats don't crowd the rare errors
    # in the recent past out of the fetch entirely -- dedup happens
    # afterwards, in _dedup_journal.
    with patch("subprocess.run", return_value=_completed("some error")) as run:
        supportinfo.collect_journal(lines=5)
    cmd = run.call_args[0][0]
    assert cmd[0] == "journalctl"
    assert "-n" in cmd
    assert cmd[cmd.index("-n") + 1] == "200"  # max(5 * 10, 200)
    assert "-p" in cmd and "err" in cmd


def test_collect_journal_scales_the_fetch_with_the_requested_line_count():
    with patch("subprocess.run", return_value=_completed("")) as run:
        supportinfo.collect_journal(lines=30)
    cmd = run.call_args[0][0]
    assert cmd[cmd.index("-n") + 1] == "300"  # 30 * 10 > the 200 floor


def test_collect_journal_passes_no_hostname_so_the_hostname_never_reaches_the_report():
    with patch("subprocess.run", return_value=_completed("")) as run:
        supportinfo.collect_journal()
    cmd = run.call_args[0][0]
    assert "--no-hostname" in cmd


def test_collect_journal_deduplicates_a_flapping_unit_and_keeps_the_count():
    repeated = "\n".join(
        f"Aug 07 09:{50 + i:02d}:00 systemd[1]: Failed to start "
        "ble-provisioning.service - HiFiBerry BLE WiFi Provisioning."
        for i in range(5)
    )
    with patch("subprocess.run", return_value=_completed(repeated)):
        result = supportinfo.collect_journal(lines=40)
    lines = result.splitlines()
    assert len(lines) == 1
    assert "Failed to start ble-provisioning.service" in lines[0]
    assert "(x5)" in lines[0]
    assert "09:54:00" in lines[0]  # the most recent occurrence's timestamp


def test_collect_journal_keeps_a_rare_error_distinct_from_a_dominant_repeat():
    # The whole point of dedup: a single distinct error must not be pushed
    # out just because another message dominates the window by volume.
    raw = "\n".join(
        ["Aug 07 09:00:00 kernel: rare disk I/O error on sda1"]
        + [
            f"Aug 07 09:{10 + i:02d}:00 systemd[1]: Failed to start "
            "ble-provisioning.service - HiFiBerry BLE WiFi Provisioning."
            for i in range(39)
        ]
    )
    with patch("subprocess.run", return_value=_completed(raw)):
        result = supportinfo.collect_journal(lines=40)
    lines = result.splitlines()
    assert len(lines) == 2
    assert "rare disk I/O error on sda1" in lines[0]
    assert "(x39)" in lines[1]
    # chronological order: the rare error was first, the repeat came after
    assert result.index("rare disk I/O error") < result.index("ble-provisioning")


def test_collect_packages_drops_entries_with_no_version():
    # dpkg knows the name (it's in a PACKAGE_PATTERNS entry) but nothing of
    # that name is installed, so dpkg-query prints the name with an empty
    # version field -- that reads as broken output in a bug report.
    raw = (
        "hifiberry-configurator 2.15.0\n"
        "librespot \n"
        "mpd \n"
        "shairport-sync \n"
        "squeezelite \n"
    )
    with patch("subprocess.run", return_value=_completed(raw)):
        result = supportinfo.collect_packages()
    assert result == "hifiberry-configurator 2.15.0"
    assert "librespot" not in result
    assert "shairport-sync" not in result


def test_collect_services_lists_audio_units():
    with patch("subprocess.run", return_value=_completed("mpd.service loaded active running")) as run:
        result = supportinfo.collect_services()
    assert "mpd.service" in result
    cmd = run.call_args[0][0]
    assert cmd[0] == "systemctl"


def test_package_patterns_drop_names_that_match_nothing_in_the_project():
    assert "audiocontrol*" not in supportinfo.PACKAGE_PATTERNS
    assert "roonbridge" not in supportinfo.PACKAGE_PATTERNS


def test_service_patterns_cover_the_units_missing_from_the_original_list():
    for pattern in (
        "nqptp*",
        "sigmatcpserver*",
        "roomeq*",
        "aes67*",
        "usbaudio*",
        "sendspin*",
        "analoginput*",
        "acr-webmcp*",
        "nowplaying-sdl*",
        "sambamount*",
    ):
        assert pattern in supportinfo.SERVICE_PATTERNS
