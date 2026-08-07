import subprocess
from unittest.mock import patch

from configurator import supportinfo


def _completed(stdout):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


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


def test_collect_packages_asks_dpkg_for_the_known_patterns():
    with patch("subprocess.run", return_value=_completed("hifiberry-configurator 2.15.0\n")) as run:
        result = supportinfo.collect_packages()
    assert result == "hifiberry-configurator 2.15.0"
    cmd = run.call_args[0][0]
    assert cmd[0] == "dpkg-query"
    assert "hifiberry-*" in cmd
    assert "mpd" in cmd


def test_collect_journal_passes_the_line_limit():
    with patch("subprocess.run", return_value=_completed("some error")) as run:
        supportinfo.collect_journal(lines=5)
    cmd = run.call_args[0][0]
    assert cmd[0] == "journalctl"
    assert "-n" in cmd and "5" in cmd
    assert "-p" in cmd and "err" in cmd


def test_collect_services_lists_audio_units():
    with patch("subprocess.run", return_value=_completed("mpd.service loaded active running")) as run:
        result = supportinfo.collect_services()
    assert "mpd.service" in result
    cmd = run.call_args[0][0]
    assert cmd[0] == "systemctl"
