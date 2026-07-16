from configurator.extensions.aptstatus import parse_status_line
from configurator.extensions.jobs import (
    PHASE_CONFIGURING,
    PHASE_DOWNLOADING,
    PHASE_INSTALLING,
)


def test_dlstatus_maps_to_downloading():
    assert parse_status_line("dlstatus:1:20.0:Retrieving hifiberry-tidal-connect") == (
        PHASE_DOWNLOADING, 20.0, "Retrieving hifiberry-tidal-connect",
    )


def test_pmstatus_maps_to_installing():
    assert parse_status_line("pmstatus:hifiberry-tidal-connect:50.0:Unpacking") == (
        PHASE_INSTALLING, 50.0, "Unpacking",
    )


def test_setting_up_maps_to_configuring():
    phase, percent, message = parse_status_line(
        "pmstatus:hifiberry-tidal-connect:90.0:Setting up hifiberry-tidal-connect"
    )
    assert phase == PHASE_CONFIGURING
    assert percent == 90.0


def test_configuring_message_maps_to_configuring():
    phase, _, _ = parse_status_line("pmstatus:pkg:80.0:Configuring pkg")
    assert phase == PHASE_CONFIGURING


def test_message_containing_colons_is_preserved():
    _, _, message = parse_status_line(
        "dlstatus:1:10.0:Get:1 http://repo.example.com trixie/main arm64"
    )
    assert message == "Get:1 http://repo.example.com trixie/main arm64"


def test_integer_percent_is_accepted():
    assert parse_status_line("dlstatus:1:20:Retrieving")[1] == 20.0


def test_pmerror_is_ignored_here():
    # Errors surface via exit code and the log, not the progress channel.
    assert parse_status_line("pmerror:pkg:0:Something broke") is None


def test_pmconffile_is_ignored():
    assert parse_status_line("pmconffile:/etc/foo.conf:0:prompt") is None


def test_unknown_kind_returns_none():
    assert parse_status_line("banana:1:2:3") is None


def test_malformed_line_returns_none():
    assert parse_status_line("dlstatus:1") is None


def test_non_numeric_percent_returns_none():
    assert parse_status_line("dlstatus:1:abc:Retrieving") is None


def test_blank_line_returns_none():
    assert parse_status_line("") is None
