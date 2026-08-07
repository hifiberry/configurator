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


def test_dedup_journal_puts_the_count_marker_at_the_start_not_the_end():
    repeated = "\n".join(
        f"Aug 07 09:{50 + i:02d}:00 systemd[1]: Failed to start "
        "ble-provisioning.service - HiFiBerry BLE WiFi Provisioning."
        for i in range(5)
    )
    with patch("subprocess.run", return_value=_completed(repeated)):
        result = supportinfo.collect_journal(lines=40)
    line = result.splitlines()[0]
    assert line.startswith("(x5)")
    assert not line.rstrip().endswith("(x5)")


def test_journal_dedup_count_survives_redaction_of_an_authorization_header_line():
    # The actual bug: redact_secrets' Authorization-header pattern is
    # deliberately greedy (a credential can contain almost any character),
    # replacing everything from the auth scheme to end of line. A count
    # marker appended at the end of the line used to fall inside that span
    # and vanish. Asserted end-to-end, through redact_secrets, not just on
    # the renderer's own output.
    raw = "\n".join(
        f"Aug 07 10:27:{i:02d} nginx[1]: auth rejected, "
        "Authorization: Basic am9lOmh1bnRlcjI="
        for i in range(37)
    )
    with patch("subprocess.run", return_value=_completed(raw)):
        deduped = supportinfo.collect_journal(lines=40)
    redacted = supportinfo.redact_secrets(deduped)
    assert "(x37)" in redacted
    assert "am9lOmh1bnRlcjI=" not in redacted
    assert "***REDACTED***" in redacted


_JOURNAL_TS_IN_OUTPUT = re.compile(r"Aug \d{2} \d{2}:\d{2}:\d{2}")


def test_dedup_journal_aligns_counted_and_uncounted_lines():
    raw = "\n".join(
        ["Aug 07 09:00:00 kernel: rare disk I/O error on sda1"]
        + [
            f"Aug 07 09:{10 + i:02d}:00 systemd[1]: Failed to start "
            "ble-provisioning.service - HiFiBerry BLE WiFi Provisioning."
            for i in range(5)
        ]
    )
    with patch("subprocess.run", return_value=_completed(raw)):
        result = supportinfo.collect_journal(lines=40)
    lines = result.splitlines()
    assert len(lines) == 2
    offsets = [_JOURNAL_TS_IN_OUTPUT.search(line).start() for line in lines]
    assert offsets[0] == offsets[1]


def test_dedup_journal_aligns_a_three_digit_count_with_a_single_digit_count():
    raw = "\n".join(
        ["Aug 07 09:00:00 systemd[1]: Failed to start ble-provisioning.service."] * 400
        + ["Aug 07 09:00:01 nginx[1]: connection reset by peer"] * 2
    )
    with patch("subprocess.run", return_value=_completed(raw)):
        result = supportinfo.collect_journal(lines=40)
    lines = result.splitlines()
    assert len(lines) == 2
    assert "(x400)" in lines[0]
    assert "(x2)" in lines[1]
    offsets = [_JOURNAL_TS_IN_OUTPUT.search(line).start() for line in lines]
    assert offsets[0] == offsets[1]


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
                            files_stdout=None, files_result=None,
                            user_units_stdout=None, user_units_result=None,
                            user_files_stdout=None, user_files_result=None):
    """subprocess.run side_effect that tells apart all four systemctl calls
    collect_services() can make: system/user x list-units/list-unit-files.

    Scope is told apart by "--user" being present in the command; the
    subcommand by which of "list-units"/"list-unit-files" appears in it (its
    position shifts depending on whether --machine=... is also present).
    """

    def run(cmd, **kwargs):
        is_user = "--user" in cmd
        if "list-units" in cmd:
            if is_user:
                if user_units_result is not None:
                    return user_units_result
                return _completed(user_units_stdout or "")
            if units_result is not None:
                return units_result
            return _completed(units_stdout or "")
        assert "list-unit-files" in cmd
        if is_user:
            if user_files_result is not None:
                return user_files_result
            return _completed(user_files_stdout or "")
        if files_result is not None:
            return files_result
        return _completed(files_stdout or "")

    return run


def _disable_user_scope():
    """Patch out the user-scope query entirely.

    Used by tests that are only exercising the system scope: without this,
    those tests would depend on whether the machine actually running them
    has /etc/hifiberry.user or a lingering user -- true on a HiFiBerryOS
    device, false (deterministically) on a dev machine or CI runner, but a
    dependency on real filesystem state that a unit test should not have
    either way.
    """
    return patch.object(
        supportinfo, "_detect_player_user", return_value=(None, "disabled for test")
    )


def _columns(line: str) -> list:
    """Split a rendered row on its column boundaries (runs of 2+ spaces)."""
    return re.split(r" {2,}", line.rstrip())


def _header_and_rows(result: str) -> tuple:
    """Split rendered output into (header, [data rows]), skipping any
    "(... unavailable: ...)" notes -- those are prose, not table rows, and
    are not expected to share the table's column count or alignment.
    """
    lines = [l for l in result.splitlines() if not l.startswith("(")]
    header = next(l for l in lines if l.startswith("SCOPE"))
    rows = [l for l in lines if l != header]
    return header, rows


def _row_for(result: str, unit: str):
    """The single rendered row whose UNIT column is exactly `unit`."""
    _, rows = _header_and_rows(result)
    matches = [r for r in rows if _columns(r)[1] == unit]
    assert len(matches) == 1, f"expected exactly one row for {unit!r}, got: {matches}"
    return matches[0]


def test_collect_services_queries_both_list_units_and_list_unit_files():
    with _disable_user_scope(), patch(
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
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="mpd.service loaded active running Music Player Daemon",
            files_stdout="mpd.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    line = _row_for(result, "mpd.service")
    assert "loaded" in line and "active" in line and "running" in line
    assert "enabled: enabled" in line


def test_collect_services_shows_an_enabled_but_not_running_unit():
    # Real diagnostic situation: the unit will start on the next boot but
    # is not running right now (crashed, never started this session, ...).
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="shairport-sync.service loaded inactive dead",
            files_stdout="shairport-sync.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()
    line = _row_for(result, "shairport-sync.service")
    assert "inactive" in line
    assert "enabled: enabled" in line


def test_collect_services_shows_a_running_but_disabled_unit():
    # Real diagnostic situation: works today, will not come back after a
    # reboot -- exactly the report this feature exists to settle.
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="mpd.service loaded active running",
            files_stdout="mpd.service disabled disabled",
        ),
    ):
        result = supportinfo.collect_services()
    line = _row_for(result, "mpd.service")
    assert "active" in line and "running" in line
    assert "enabled: disabled" in line


def test_collect_services_drops_units_neither_installed_nor_enabled():
    # squeezelite is a SERVICE_PATTERNS entry but is not installed on most
    # systems -- systemctl reports it "not-found" in both calls, and that
    # combination must not survive into the report as noise.
    with _disable_user_scope(), patch(
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
    with _disable_user_scope(), patch(
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
    assert "system enabled state unavailable" in result


def test_collect_services_keeps_enabled_state_when_list_units_fails():
    with _disable_user_scope(), patch(
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
    assert "system running state unavailable" in result


def test_service_rows_for_scope_never_treats_a_failure_as_not_found():
    # Direct check on the per-scope merge function: even if both calls
    # fail, no unit can be reported as "not-found" from that -- there is
    # simply no data.
    rows, notes = supportinfo._service_rows_for_scope(
        "system", "(command failed: no systemctl)", "(command failed: no systemctl)"
    )
    assert rows == []
    assert any("running state unavailable" in n for n in notes)
    assert any("enabled state unavailable" in n for n in notes)


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
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    header, rows = _header_and_rows(result)
    table_lines = [header] + rows
    assert len(table_lines) > 1  # a header plus at least one row
    column_counts = {len(_columns(line)) for line in table_lines}
    assert len(column_counts) == 1, f"ragged columns: {table_lines}"


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
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    header, rows = _header_and_rows(result)
    enabled_offsets = {
        line.index("ENABLED" if line is header else "[enabled:")
        for line in [header] + rows
    }
    assert len(enabled_offsets) == 1, f"misaligned ENABLED column: {result}"


def test_collect_services_strips_the_systemctl_status_glyph():
    units_stdout = "● shairport-sync.service not-found inactive dead"
    files_stdout = "shairport-sync.service enabled enabled"
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    assert "●" not in result  # "●"
    # The glyph must not have swallowed the unit name into the LOAD field.
    line = _row_for(result, "shairport-sync.service")
    assert "not-found" in line
    assert "enabled: enabled" in line


def test_collect_services_strips_a_status_glyph_with_leading_whitespace():
    # Same bug class as the unanchored-past-whitespace case: real hardware
    # puts the glyph at column 0, but the parser must not depend on that.
    units_stdout = "  ● shairport-sync.service not-found inactive dead"
    files_stdout = "shairport-sync.service enabled enabled"
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    assert "●" not in result
    line = _row_for(result, "shairport-sync.service")
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
    with _disable_user_scope(), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(units_stdout=units_stdout, files_stdout=files_stdout),
    ):
        result = supportinfo.collect_services()

    header, _ = _header_and_rows(result)
    raat_line = _row_for(result, "hifiberry-raat.service")
    mpd_line = _row_for(result, "mpd.service")

    assert len(_columns(raat_line)) == len(_columns(header))
    assert len(_columns(raat_line)) == len(_columns(mpd_line))
    columns = _columns(raat_line)
    assert "not-found" in columns  # LOAD: no running-state entry
    assert columns.count("-") == 2  # ACTIVE and SUB: explicit placeholders
    assert "enabled: static" in raat_line


# --- The player user's systemd --user instance ---------------------------
#
# On HiFiBerryOS the player daemons run as systemd *user* services under a
# dedicated account, not as system services -- the system scope alone is
# silent for exactly the reports that matter most (a player bug). These
# tests cover: finding that account (primary source, fallback, neither
# available), choosing --user vs --machine=<user>@.host depending on who
# config-supportinfo itself runs as, keeping the two scopes from colliding
# on a shared unit name, an unreachable user instance not being fatal to
# the system half, and the alignment property holding once both scopes are
# mixed into the same table.


def test_detect_player_user_reads_the_hifiberry_user_file():
    with patch.object(supportinfo, "_read_hifiberry_user_file", return_value="matuschd"):
        user, source = supportinfo._detect_player_user()
    assert user == "matuschd"
    # The source names *how* detection happened, not the username -- see
    # the privacy tests below.
    assert source == "from /etc/hifiberry.user"


def test_detect_player_user_falls_back_to_the_linger_directory():
    # Older images may not carry /etc/hifiberry.user; the player user must
    # have systemd linger enabled regardless (its services could not
    # otherwise survive a reboot without an interactive login), so a
    # single lingering user is the next best signal.
    with patch.object(supportinfo, "_read_hifiberry_user_file", side_effect=OSError("no such file")), \
         patch.object(supportinfo, "_list_linger_users", return_value=["matuschd"]):
        user, source = supportinfo._detect_player_user()
    assert user == "matuschd"
    assert source == "from linger (single account)"


def test_detect_player_user_reports_unavailable_when_neither_source_resolves():
    with patch.object(supportinfo, "_read_hifiberry_user_file", side_effect=OSError("no such file")), \
         patch.object(supportinfo, "_list_linger_users", side_effect=OSError("no such directory")):
        user, reason = supportinfo._detect_player_user()
    assert user is None
    assert reason  # a human-readable explanation, not silence
    assert "no player user" in reason


def test_detect_player_user_reports_unavailable_when_linger_is_ambiguous():
    # More than one lingering user and no /etc/hifiberry.user to break the
    # tie: guessing which one runs the players would risk querying the
    # wrong (or an innocent bystander's) session, so this is unavailable
    # too, not a coin flip.
    with patch.object(supportinfo, "_read_hifiberry_user_file", side_effect=OSError("no such file")), \
         patch.object(supportinfo, "_list_linger_users", return_value=["alice", "bob"]):
        user, reason = supportinfo._detect_player_user()
    assert user is None
    assert "ambiguous" in reason
    # The candidate names themselves must not leak into the report either.
    assert "alice" not in reason and "bob" not in reason


def test_read_hifiberry_user_file_skips_blank_and_comment_lines():
    fake_lines = ["# the player user\n", "\n", "matuschd\n"]
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value = fake_lines
        name = supportinfo._read_hifiberry_user_file()
    assert name == "matuschd"


def test_read_hifiberry_user_file_falls_through_on_a_comment_only_file():
    # Real bug: a comment-only file used to return "# the player user"
    # verbatim as the username, producing a bogus --machine target and an
    # unavailable user scope instead of correctly falling through to the
    # linger directory.
    fake_lines = ["# the player user\n", "\n"]
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value = fake_lines
        name = supportinfo._read_hifiberry_user_file()
    assert name == ""


def test_read_hifiberry_user_file_falls_through_on_an_invalid_username():
    fake_lines = ["this is not a username\n"]
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value = fake_lines
        name = supportinfo._read_hifiberry_user_file()
    assert name == ""


def test_detect_player_user_falls_back_to_linger_on_a_comment_only_file():
    with patch.object(supportinfo, "_read_hifiberry_user_file", return_value=""), \
         patch.object(supportinfo, "_list_linger_users", return_value=["matuschd"]):
        user, source = supportinfo._detect_player_user()
    assert user == "matuschd"
    assert source == "from linger (single account)"


def test_collect_user_services_uses_plain_user_flag_when_already_that_user():
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="matuschd"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )) as run:
        _, notes = supportinfo._collect_user_service_rows()

    commands = [call.args[0] for call in run.call_args_list]
    assert len(commands) == 2
    for cmd in commands:
        assert cmd[0] == "systemctl"
        assert "--user" in cmd
        assert not any(arg.startswith("--machine=") for arg in cmd)
    # The report records which of the two access paths was actually taken,
    # so a reader can tell a same-user collection from a --machine one.
    assert "access: direct session bus" in notes[0]


def test_collect_user_services_uses_machine_flag_when_a_different_user():
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )) as run:
        _, notes = supportinfo._collect_user_service_rows()

    commands = [call.args[0] for call in run.call_args_list]
    assert len(commands) == 2
    for cmd in commands:
        assert cmd[0] == "systemctl"
        assert "--user" in cmd
        assert "--machine=matuschd@.host" in cmd
    # Same note, but naming the other access path -- this is the case that
    # matters most, since it is what config-server (always running as
    # root) always takes.
    assert "access: via --machine" in notes[0]


def test_collect_services_distinguishes_same_named_units_by_scope():
    # The name-collision case the coordinator flagged: a system-scope
    # mpd.service that doesn't exist, and a user-scope mpd.service that is
    # installed, enabled and running. Both must render, distinctly, rather
    # than one clobbering the other.
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="● mpd.service not-found inactive dead",
             files_stdout="",
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )):
        result = supportinfo.collect_services()

    _, rows = _header_and_rows(result)
    mpd_rows = [r for r in rows if _columns(r)[1] == "mpd.service"]
    # The system-scope not-found/not-found mpd.service is suppressed as
    # noise (same rule as before); only the real, running user unit shows.
    assert len(mpd_rows) == 1
    scope, unit, load, active, sub = _columns(mpd_rows[0])[:5]
    assert scope == "user"
    assert active == "active" and sub == "running"
    assert "enabled: enabled" in mpd_rows[0]


def test_collect_services_shows_both_scopes_of_a_genuinely_colliding_unit():
    # Same unit name present -- and *not* suppressed -- in both scopes at
    # once: both rows must survive, tagged distinctly, never merged.
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="mpd.service loaded active running",
             files_stdout="mpd.service enabled enabled",
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )):
        result = supportinfo.collect_services()

    _, rows = _header_and_rows(result)
    mpd_rows = [r for r in rows if _columns(r)[1] == "mpd.service"]
    assert len(mpd_rows) == 2
    scopes = {_columns(r)[0] for r in mpd_rows}
    assert scopes == {"system", "user"}


def test_collect_services_reports_unreachable_user_instance_without_dropping_the_system_half():
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="config-server.service loaded active running",
             files_stdout="config-server.service enabled enabled",
             user_units_result=_failed("Failed to connect to bus: Host is down"),
             user_files_result=_failed("Failed to connect to bus: Host is down"),
         )):
        result = supportinfo.collect_services()

    assert "config-server.service" in result
    assert _row_for(result, "config-server.service")
    assert "user running state unavailable" in result
    assert "user enabled state unavailable" in result
    assert "Host is down" in result


def test_collect_services_reports_missing_player_user_without_being_fatal():
    with patch.object(
        supportinfo, "_detect_player_user",
        return_value=(None, "no player user found (test)"),
    ), patch(
        "subprocess.run",
        side_effect=_systemctl_side_effect(
            units_stdout="config-server.service loaded active running",
            files_stdout="config-server.service enabled enabled",
        ),
    ):
        result = supportinfo.collect_services()

    assert "config-server.service" in result
    assert "user services unavailable" in result
    assert "no player user found (test)" in result


def test_collect_services_alignment_holds_across_mixed_scope_rows():
    with patch.object(supportinfo, "_detect_player_user", return_value=("matuschd", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="\n".join([
                 "config-server.service loaded active running",
                 "sigmatcpserver.service loaded active running",
             ]),
             files_stdout="\n".join([
                 "config-server.service enabled enabled",
                 "sigmatcpserver.service enabled enabled",
             ]),
             user_units_stdout="\n".join([
                 "mpd.service loaded active running",
                 "librespot.service loaded active running",
                 "shairport.service loaded inactive dead",
             ]),
             user_files_stdout="\n".join([
                 "mpd.service enabled enabled",
                 "librespot.service enabled enabled",
                 "shairport.service enabled enabled",
             ]),
         )):
        result = supportinfo.collect_services()

    header, rows = _header_and_rows(result)
    assert len(rows) == 5  # 2 system rows + 3 user rows
    table_lines = [header] + rows
    column_counts = {len(_columns(line)) for line in table_lines}
    assert len(column_counts) == 1, f"ragged columns: {table_lines}"
    enabled_offsets = {
        line.index("ENABLED" if line is header else "[enabled:")
        for line in table_lines
    }
    assert len(enabled_offsets) == 1, f"misaligned ENABLED column: {result}"
    scopes = {_columns(r)[0] for r in rows}
    assert scopes == {"system", "user"}
    # And the note above the table names the detection source, not the
    # account itself, plus which access path was used to reach it.
    assert "(user scope: from /etc/hifiberry.user; access: via --machine)" in result
    assert "matuschd" not in result


# --- Privacy: the detection is auditable, the username is not ----------
#
# A reviewer noted the report never said which account got queried, so a
# wrong guess would be undetectable -- but the username itself must never
# appear either: it is a real person's login name on every device seen so
# far, the same reason the hostname is already left out, and this report
# is meant to be pasted into a public issue. The fix names the *source* of
# the detection (which file/heuristic found it), not its result.


def test_collect_services_notes_the_file_detection_source():
    with patch.object(supportinfo, "_detect_player_user", return_value=("realname", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="", files_stdout="",
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )):
        result = supportinfo.collect_services()
    assert "(user scope: from /etc/hifiberry.user; access: via --machine)" in result
    assert "realname" not in result


def test_collect_services_notes_the_linger_detection_source():
    with patch.object(supportinfo, "_detect_player_user", return_value=("realname", "from linger (single account)")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="", files_stdout="",
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )):
        result = supportinfo.collect_services()
    assert "(user scope: from linger (single account); access: via --machine)" in result
    assert "realname" not in result


def test_collect_services_notes_the_ambiguous_detection_failure():
    with patch.object(
        supportinfo, "_detect_player_user",
        return_value=(None, "ambiguous player user: 2 lingering users found, none chosen"),
    ), patch("subprocess.run", side_effect=_systemctl_side_effect(units_stdout="", files_stdout="")):
        result = supportinfo.collect_services()
    assert "(user services unavailable: ambiguous player user:" in result
    assert "none chosen" in result


def test_collect_services_notes_the_no_user_found_detection_failure():
    with patch.object(
        supportinfo, "_detect_player_user",
        return_value=(None, "no player user found (/etc/hifiberry.user missing and no lingering user in /var/lib/systemd/linger/)"),
    ), patch("subprocess.run", side_effect=_systemctl_side_effect(units_stdout="", files_stdout="")):
        result = supportinfo.collect_services()
    assert "(user services unavailable: no player user found" in result


def test_collect_services_never_prints_the_player_username():
    # The property the coordinator asked to depend on, exercised across a
    # realistic run: the account is found (via the file), used to build a
    # --machine target, and successfully queried -- the only place a real
    # username could leak into the report.
    with patch.object(supportinfo, "_detect_player_user", return_value=("mrsmith", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="config-server.service loaded active running",
             files_stdout="config-server.service enabled enabled",
             user_units_stdout="mpd.service loaded active running",
             user_files_stdout="mpd.service enabled enabled",
         )):
        result = supportinfo.collect_services()
    assert "mrsmith" not in result
    assert "config-server.service" in result and "mpd.service" in result


def test_collect_services_scrubs_the_username_from_a_machine_connection_failure():
    # systemctl's own failure text for --machine=<user>@.host routinely
    # echoes the machine spec back (e.g. "Failed to connect to machine
    # mrsmith@.host: Host is down") -- that text flows straight into a
    # "(command failed: ...)" note via _run(), which is not otherwise
    # redacted (redact_secrets targets credentials, not usernames). The
    # username must not survive into the rendered report through that path
    # either.
    with patch.object(supportinfo, "_detect_player_user", return_value=("mrsmith", "from /etc/hifiberry.user")), \
         patch.object(supportinfo, "_current_user", return_value="root"), \
         patch("subprocess.run", side_effect=_systemctl_side_effect(
             units_stdout="config-server.service loaded active running",
             files_stdout="config-server.service enabled enabled",
             user_units_result=_failed("Failed to connect to machine mrsmith@.host: Host is down"),
             user_files_result=_failed("Failed to connect to machine mrsmith@.host: Host is down"),
         )):
        result = supportinfo.collect_services()
    assert "mrsmith" not in result
    assert "Host is down" in result  # the rest of the failure reason survives
    assert "user running state unavailable" in result
