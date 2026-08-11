"""A factory reset also restores the players the user switched off.

Which players are enabled lives in systemd, not in the configuration database,
so clearing the database is not enough - see reset_managed_services().
"""

import pytest

from configurator.handlers import systemd_handler as systemd_handler_module
from configurator.handlers.systemd_handler import SystemdHandler


class FakeServiceManager:
    def __init__(self, failing=()):
        self.enabled = []
        self.failing = set(failing)

    def enable(self, service):
        if service in self.failing:
            return False, f"Failed to enable service '{service}': boom"
        self.enabled.append(service)
        return True, "ok"


@pytest.fixture
def handler(monkeypatch):
    monkeypatch.setattr(
        systemd_handler_module, "get_config_section",
        lambda section, default=None: {
            "raat": "all",
            "shairport": "all",
            "librespot": "all",
            "config-server": "status",  # read-only, must not be touched
        },
    )
    handler = SystemdHandler.__new__(SystemdHandler)
    handler.allowed_operations = {
        'all': ['start', 'stop', 'restart', 'enable', 'disable',
                'enable-now', 'disable-now', 'status'],
        'status': ['status'],
    }
    handler.service_manager = FakeServiceManager()
    handler._installed = {"raat", "shairport", "librespot", "config-server"}
    monkeypatch.setattr(
        SystemdHandler, "_service_exists",
        lambda self, service: service in self._installed,
    )
    return handler


def test_reset_enables_every_controllable_service(handler):
    result = handler.reset_managed_services()

    assert result['status'] == 'success'
    assert sorted(handler.service_manager.enabled) == ["librespot", "raat", "shairport"]
    assert result['failed'] == {}


def test_reset_leaves_read_only_services_alone(handler):
    """Only services the web UI can toggle are reset - nothing else."""
    handler.reset_managed_services()

    assert "config-server" not in handler.service_manager.enabled


def test_reset_skips_services_that_are_not_installed(handler):
    handler._installed = {"raat"}

    result = handler.reset_managed_services()

    assert handler.service_manager.enabled == ["raat"]
    assert sorted(result['not_installed']) == ["librespot", "shairport"]


def test_reset_reports_a_failing_service_without_giving_up(handler):
    handler.service_manager = FakeServiceManager(failing={"raat"})

    result = handler.reset_managed_services()

    assert result['status'] == 'partial'
    assert "raat" in result['failed']
    # The other players are still reset
    assert sorted(handler.service_manager.enabled) == ["librespot", "shairport"]
