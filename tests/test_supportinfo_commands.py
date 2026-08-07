import re
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


def test_package_patterns_cover_units_that_are_also_in_service_patterns():
    # Final review, finding 2: roomeq and nowplaying-sdl were in
    # SERVICE_PATTERNS (an earlier fix round updated the service list only),
    # so a DSP bug report showed the roomeq unit running but no roomeq
    # version.
    assert "roomeq" in supportinfo.PACKAGE_PATTERNS
    assert "nowplaying-sdl" in supportinfo.PACKAGE_PATTERNS


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


# --- Enabled state (systemctl list-unit-files) --------------------------
#
# collect_services() used to report only whether a unit was running right
# now (systemctl list-units). It did not say whether the unit would start
# again after a reboot -- the "player works until I reboot, then it
# doesn't" report is settled by the enabled state, not by what happens to
# be running at the moment someone runs config-supportinfo. These tests
# cover the merged output: both systemctl calls fire with the right
# arguments, running and enabled state land in the same row, an
# enabled-but-not-running unit and a running-but-disabled unit are both
# shown (they are real, distinct diagnostic situations), noise from units
# that are neither installed nor enabled is dropped, and a failing
# list-unit-files call leaves the running-state half of the report intact.


def _systemctl_side_effect(units_stdout=None, units_result=None,
                            files_stdout=None, files_result=None):
    """subprocess.run side_effect that tells list-units and list-unit-files apart."""

    def run(cmd, **kwargs):
        if cmd[1] == "list-units":
            if units_result is not None:
                return units_result
            return _completed(units_stdout or "")
        assert cmd[1] == "list-unit-files"
        if files_result is not None:
            return files_result
        return _completed(files_stdout or "")

    return run


def test_collect_services_queries_both_list_units_and_list_unit_files():
    with patch(
        "subprocess.run", side_effect=_systemctl_side_effect()
    ) as run:
        supportinfo.collect_services()
    assert run.call_count == 2
    commands = [call.args[0] for call in run.call_args_list]

    units_cmd = next(c for c in commands if c[1] == "list-units")
    assert units_cmd[0] == "systemctl"
    assert "--all" in units_cmd
    assert "--no-legend" in units_cmd
    assert "--no-pager" in units_cmd
    assert "mpd*" in units_cmd

    files_cmd = next(c for c in commands if c[1] == "list-unit-files")
    assert files_cmd[0] == "systemctl"
    assert "--no-legend" in files_cmd
    assert "--no-pager" in files_cmd
    assert "mpd*" in files_cmd
    # list-unit-files has no running units to enumerate, so it takes no --all
    assert "--all" not in files_cmd


def test_collect_services_merges_running_and_enabled_state_in_one_row():
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="mpd.service loaded active running Music Player Daemon",
            files_stdout="mpd.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    lines = [l for l in result.splitlines() if l.startswith("mpd.service")]
    assert len(lines) == 1
    line = lines[0]
    assert "loaded" in line and "active" in line and "running" in line
    assert "enabled" in line


def test_collect_services_shows_an_enabled_but_not_running_unit():
    # Real diagnostic situation: the unit will start on the next boot but
    # is not running right now (crashed, never started this session, ...).
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="shairport-sync.service loaded inactive dead",
            files_stdout="shairport-sync.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    line = next(l for l in result.splitlines() if l.startswith("shairport-sync.service"))
    assert "inactive" in line
    assert "enabled: enabled" in line


def test_collect_services_shows_a_running_but_disabled_unit():
    # Real diagnostic situation: works today, will not come back after a
    # reboot -- exactly the report this feature exists to settle.
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="mpd.service loaded active running",
            files_stdout="mpd.service disabled disabled",
        ),
    ):
        result = supportinfo.collect_services()
    line = next(l for l in result.splitlines() if l.startswith("mpd.service"))
    assert "active" in line and "running" in line
    assert "enabled: disabled" in line


def test_collect_services_drops_units_neither_installed_nor_enabled():
    # squeezelite is a SERVICE_PATTERNS entry but is not installed on most
    # systems -- systemctl reports it "not-found" in both calls, and that
    # combination must not survive into the report as noise.
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout=(
                "mpd.service loaded active running\n"
                "squeezelite.service not-found inactive dead"
            ),
            files_stdout="mpd.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    assert "squeezelite" not in result
    assert "mpd.service" in result


def test_collect_services_keeps_running_state_when_list_unit_files_fails():
    # _run() reports failures as strings rather than raising; a missing or
    # failing systemctl on one call must not blank out the other half of
    # the report.
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="mpd.service loaded active running",
            files_result=_failed("systemctl: command not found"),
        ),
    ):
        result = supportinfo.collect_services()
    assert "mpd.service" in result
    assert "active" in result and "running" in result
    assert "enabled: unknown" in result
    assert "enabled state unavailable" in result


def test_collect_services_keeps_enabled_state_when_list_units_fails():
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_result=_failed("Failed to list units: access denied"),
            files_stdout="mpd.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    assert "mpd.service" in result
    assert "enabled: enabled" in result
    assert "unknown" in result
    assert "running state unavailable" in result


def test_merge_service_states_never_treats_a_failure_as_not_found():
    # Direct check on the merge function: even if both calls fail, no unit
    # can be reported as "not-found" from that -- there is simply no data.
    result = supportinfo._merge_service_states(
        "(command failed: no systemctl)", "(command failed: no systemctl)"
    )
    assert "not-found" not in result
    assert "running state unavailable" in result
    assert "enabled state unavailable" in result


# --- Rendering: alignment, glyph stripping, column placeholders ---------
#
# Real hardware output surfaced three rendering-only bugs the mocked tests
# above never exercised: systemctl's leading "●" glyph on a not-found unit
# shifted every field in that row over by one; a unit that only appeared
# in list-unit-files (never in list-units) collapsed its running-state
# placeholder to a single word instead of occupying the normal three
# columns; and nothing was actually padded, so columns did not line up.
# These tests assert the alignment *property* -- not a golden string --
# so they keep catching a regression without breaking on the next
# unrelated wording change.

def _columns(line: str) -> list:
    """Split a rendered row on its column boundaries (runs of 2+ spaces)."""
    return re.split(r" {2,}", line.rstrip())


def test_collect_services_rows_share_the_same_column_count_as_the_header():
    units_stdout = "\n".join([
        "mpd.service loaded active running Music Player Daemon",
        "sambamount.service loaded active exited Samba Mount",
        "● shairport-sync.service not-found inactive dead",
    ])
    files_stdout = "\n".join([
        "mpd.service disabled disabled",
        "sambamount.service enabled enabled",
        "hifiberry-raat.service static enabled",
    ])
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    lines = result.splitlines()
    assert len(lines) > 1  # a header plus at least one row
    column_counts = {len(_columns(line)) for line in lines}
    assert len(column_counts) == 1, f"ragged columns: {lines}"


def test_collect_services_enabled_column_starts_at_the_same_offset_on_every_row():
    units_stdout = "\n".join([
        "mpd.service loaded active running",
        "sambamount.service loaded active exited",
    ])
    files_stdout = "\n".join([
        "mpd.service disabled disabled",
        "sambamount.service enabled enabled",
        "hifiberry-raat.service static enabled",
    ])
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    header, *rows = result.splitlines()
    enabled_offsets = {line.index("ENABLED" if line is header else "[enabled:") for line in [header] + rows}
    assert len(enabled_offsets) == 1, f"misaligned ENABLED column: {result}"


def test_collect_services_strips_the_systemctl_status_glyph():
    units_stdout = "● shairport-sync.service not-found inactive dead"
    files_stdout = "shairport-sync.service enabled enabled"
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    assert "●" not in result  # "●"
    # The glyph must not have swallowed the unit name into the LOAD field.
    line = next(l for l in result.splitlines() if l.startswith("shairport-sync.service"))
    assert "not-found" in line
    assert "enabled: enabled" in line


def test_collect_services_unit_missing_running_state_still_occupies_its_columns():
    # hifiberry-raat.service only appears in list-unit-files (a static unit
    # with no loaded instance) -- it must still render the same number of
    # columns as a unit with full running-state data, with an explicit
    # placeholder rather than a collapsed/missing field.
    units_stdout = "mpd.service loaded active running"
    files_stdout = "\n".join([
        "mpd.service enabled enabled",
        "hifiberry-raat.service static enabled",
    ])
    with patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    lines = result.splitlines()
    header, *rows = lines
    raat_line = next(l for l in rows if l.startswith("hifiberry-raat.service"))
    mpd_line = next(l for l in rows if l.startswith("mpd.service"))

    assert len(_columns(raat_line)) == len(_columns(header))
    assert len(_columns(raat_line)) == len(_columns(mpd_line))
    columns = _columns(raat_line)
    assert "not-found" in columns  # LOAD: no running-state entry
    assert columns.count("-") == 2  # ACTIVE and SUB: explicit placeholders
    assert "enabled: static" in raat_line
