from configurator.extensions.postinstall import refresh_system_state


class FakeServiceManager:
    def __init__(self, daemon_reload_ok=True):
        self.calls = []
        self._daemon_reload_ok = daemon_reload_ok

    def daemon_reload(self):
        self.calls.append("daemon_reload")
        return (self._daemon_reload_ok, "" if self._daemon_reload_ok else "boom")

    def refresh_service_map(self):
        self.calls.append("refresh_service_map")


def test_runs_all_three_steps_in_order():
    manager = FakeServiceManager()
    reloaded = []

    steps = refresh_system_state(
        service_manager=manager,
        config_reloader=lambda: reloaded.append(True),
    )

    assert manager.calls == ["daemon_reload", "refresh_service_map"]
    assert reloaded == [True]
    assert steps == ["daemon-reload", "reload-config", "rescan-services"]


def test_config_reloader_is_called_even_if_daemon_reload_fails():
    # A failed daemon-reload must not strand the new conf.d drop-in.
    manager = FakeServiceManager(daemon_reload_ok=False)
    reloaded = []

    steps = refresh_system_state(
        service_manager=manager,
        config_reloader=lambda: reloaded.append(True),
    )

    assert reloaded == [True]
    assert "reload-config" in steps
    assert "daemon-reload" not in steps


def test_a_raising_step_does_not_prevent_the_others():
    manager = FakeServiceManager()

    def boom():
        raise RuntimeError("config file vanished")

    steps = refresh_system_state(service_manager=manager, config_reloader=boom)

    assert "reload-config" not in steps
    assert "rescan-services" in steps


def test_missing_service_manager_still_reloads_config():
    reloaded = []
    steps = refresh_system_state(
        service_manager=None,
        config_reloader=lambda: reloaded.append(True),
    )
    assert reloaded == [True]
    assert steps == ["reload-config"]
