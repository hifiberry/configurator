"""Enabling and disabling user services has to happen in the system scope.

The packages enable their user units in /etc/systemd/user/*.wants, which belongs
to root. 'systemctl --user' running as the audio user only manages the links
below its home directory, so a disable there reported success while the unit
stayed enabled and came back on the next boot.
"""

import pytest

from configurator.systemd_service import SystemdServiceManager


class FakeManager(SystemdServiceManager):
    """A manager with a recorded, always-successful _run_command."""

    def __init__(self, environments):
        self.systemctl_cmd = "systemctl"
        self.user_name = "audio"
        self.user_uid = 1001
        self.user_runtime_dir = "/run/user/1001"
        self.service_environments = dict(environments)
        self.commands = []
        self.failures = set()

    def _run_command(self, command, env=None):
        self.commands.append(command)
        if tuple(command) in self.failures:
            return False, "", "boom"
        return True, "", ""


@pytest.fixture
def manager():
    return FakeManager({"raat": "user", "sambamount": "system"})


def _commands_containing(manager, verb):
    return [c for c in manager.commands if verb in c]


def test_enable_user_service_uses_global_scope(manager):
    success, _ = manager.enable("raat")

    assert success
    enable_cmds = _commands_containing(manager, "enable")
    assert enable_cmds == [["systemctl", "--global", "enable", "raat"]]


def test_disable_user_service_clears_both_link_sets(manager):
    success, _ = manager.disable("raat")

    assert success
    disable_cmds = _commands_containing(manager, "disable")
    # The root-owned link in /etc/systemd/user...
    assert ["systemctl", "--global", "disable", "raat"] in disable_cmds
    # ...and any leftover in the user's home, from older versions
    assert any("--user" in cmd and "disable" in cmd for cmd in disable_cmds)


def test_disable_user_service_reports_failure_of_the_global_scope(manager):
    manager.failures.add(("systemctl", "--global", "disable", "raat"))

    success, message = manager.disable("raat")

    assert not success
    assert "raat" in message


def test_disable_user_service_survives_a_failing_user_manager(manager):
    """The per-user cleanup is opportunistic - the link is usually not there."""
    manager.failures.add(tuple([
        "systemd-run", "--uid", "1001", "--gid", "1001",
        "--setenv", "XDG_RUNTIME_DIR=/run/user/1001",
        "--pipe", "--wait", "--quiet", "--collect",
        "systemctl", "--user", "disable", "raat",
    ]))

    success, _ = manager.disable("raat")

    assert success


def test_enablement_of_system_services_is_unchanged(manager):
    manager.enable("sambamount")
    manager.disable("sambamount")

    assert ["systemctl", "enable", "sambamount"] in manager.commands
    assert ["systemctl", "disable", "sambamount"] in manager.commands
    assert not any("--global" in cmd for cmd in manager.commands)


def test_start_and_stop_still_run_as_the_user(manager):
    manager.start("raat")
    manager.stop("raat")

    for verb in ("start", "stop"):
        cmd = _commands_containing(manager, verb)[0]
        assert cmd[0] == "systemd-run"
        assert "--user" in cmd
