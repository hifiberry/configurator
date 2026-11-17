"""Factory reset of the audio server state."""

import pytest

from configurator import audio_server


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def env(tmp_path, monkeypatch):
    command = tmp_path / "hifiberry-audio-server"
    state = tmp_path / "state.toml"
    monkeypatch.setattr(audio_server, "COMMAND", str(command))
    monkeypatch.setattr(audio_server, "CHOICE_PATH", str(tmp_path / "choice"))
    monkeypatch.setattr(audio_server, "STATE_PATH", str(state))
    monkeypatch.setattr(audio_server, "PIPEWIRE_RESET_MARKER",
                        str(tmp_path / "var" / "pipewire-reset-pending"))
    return command, state


def install(command):
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)


def fake_run(monkeypatch, state, active=True, fail=(), calls=None):
    """Record calls; `fail` holds argv tuples that exit 1."""
    def run(cmd, **kwargs):
        assert isinstance(cmd, list)
        assert not kwargs.get("shell")
        assert kwargs.get("timeout")
        key = tuple(cmd[1:])
        if calls is not None:
            calls.append(key if cmd[0] != "systemctl" else ("systemctl",) + key)
            if key == ("start", "aas.service") or key == ("stop", "aas.service"):
                calls.append(("state_exists", state.exists()))
        if key == ("is-active", "--quiet", "aas.service"):
            return Completed(0 if active else 3)
        if key in fail:
            return Completed(1, stderr="boom")
        if cmd[0] != "systemctl" and key == ("get",):
            return Completed(0, "running pipewire\n")
        return Completed(0)
    monkeypatch.setattr(audio_server.subprocess, "run", run)


def test_unavailable(env, monkeypatch):
    _, state = env
    calls = []
    fake_run(monkeypatch, state, calls=calls)
    state.write_text("x")
    assert audio_server.reset() == {"status": "unavailable",
                                    "reboot_required": False}
    assert calls == []
    assert state.exists()


def test_active(env, monkeypatch):
    command, state = env
    install(command)
    state.write_text("x")
    calls = []
    fake_run(monkeypatch, state, active=True, calls=calls)
    assert audio_server.reset()["status"] == "success"
    relevant = [c for c in calls if c[0] in ("systemctl", "set")
                and c[1:2] != ("is-active",)]
    assert relevant == [("systemctl", "stop", "aas.service"),
                        ("systemctl", "start", "aas.service"),
                        ("set", "pipewire")]
    # the state file was gone by the time aas started again
    assert ("state_exists", False) in calls
    assert not state.exists()


def test_inactive(env, monkeypatch):
    command, state = env
    install(command)
    state.write_text("x")
    calls = []
    fake_run(monkeypatch, state, active=False, calls=calls)
    assert audio_server.reset()["status"] == "success"
    assert not any(c[0] == "systemctl" and c[1] in ("stop", "start") for c in calls)
    assert ("set", "pipewire") in calls
    assert not state.exists()


def test_no_state_file_is_fine(env, monkeypatch):
    command, state = env
    install(command)
    fake_run(monkeypatch, state, active=False)
    assert audio_server.reset()["status"] == "success"


def test_failing_step_reported_rest_runs(env, monkeypatch):
    command, state = env
    install(command)
    state.write_text("x")
    calls = []
    fake_run(monkeypatch, state, active=True, fail={("stop", "aas.service")},
             calls=calls)
    result = audio_server.reset()
    assert result["status"] == "error"
    assert "stop aas.service" in result["message"]
    # stopping failed: the state file stays, and says so
    assert state.exists()
    assert "remove saved state" in result["message"]
    assert ("systemctl", "start", "aas.service") in calls
    assert ("set", "pipewire") in calls


def test_failing_set_reported(env, monkeypatch):
    command, state = env
    install(command)
    fake_run(monkeypatch, state, active=False, fail={("set", "pipewire")})
    result = audio_server.reset()
    assert result["status"] == "error"
    assert "boom" in result["message"]


def test_unexpected_exception_does_not_escape(env, monkeypatch):
    command, state = env
    install(command)
    fake_run(monkeypatch, state, active=False)

    def boom():
        raise ValueError("odd")
    monkeypatch.setattr(audio_server, "_set_server", lambda s: boom())
    result = audio_server.reset()
    assert result["status"] == "error"
    assert "odd" in result["message"]


def marker():
    return audio_server.PIPEWIRE_RESET_MARKER


import os


@pytest.mark.parametrize("active,chosen,reached,written", [
    (True, "pipewire", False, True),
    (False, "aas", False, True),
    (True, "aas", True, False),
    (False, "pipewire", False, False),
])
def test_marker_written_when_pipewire_api_was_not_reached(
        env, monkeypatch, tmp_path, active, chosen, reached, written):
    command, state = env
    install(command)
    (tmp_path / "choice").write_text(chosen + "\n")
    fake_run(monkeypatch, state, active=active)
    audio_server.reset(pipewire_reached=reached)
    assert os.path.exists(marker()) is written


@pytest.mark.parametrize("active,switched,expected", [
    (True, True, True), (False, True, False), (True, False, False)])
def test_reboot_required(env, monkeypatch, active, switched, expected):
    command, state = env
    install(command)
    fake_run(monkeypatch, state, active=active,
             fail=set() if switched else {("set", "pipewire")})
    assert audio_server.reset()["reboot_required"] is expected


def test_retry_loop_removes_marker_on_success(env):
    os.makedirs(os.path.dirname(marker()))
    open(marker(), "w").close()
    results = iter([{"status": "unavailable"}, {"status": "unavailable"},
                    {"status": "success"}])
    sleeps = []
    assert audio_server.retry_pipewire_reset(
        lambda: next(results), sleep=sleeps.append) is True
    assert sleeps == [5, 5]
    assert not os.path.exists(marker())


def test_retry_loop_gives_up_and_keeps_marker(env):
    os.makedirs(os.path.dirname(marker()))
    open(marker(), "w").close()
    calls, sleeps = [], []

    def fake():
        calls.append(1)
        return {"status": "unavailable"}
    assert audio_server.retry_pipewire_reset(fake, sleep=sleeps.append) is False
    assert sum(sleeps) == 180 and len(calls) == 37
    assert os.path.exists(marker())


def test_no_thread_without_marker(env):
    assert audio_server.start_pending_pipewire_reset(lambda: {}) is None


def test_thread_started_with_marker(env):
    os.makedirs(os.path.dirname(marker()))
    open(marker(), "w").close()
    t = audio_server.start_pending_pipewire_reset(
        lambda: {"status": "success"}, sleep=lambda s: None)
    t.join(5)
    assert t.daemon and not os.path.exists(marker())


def test_route_carries_audio_server(env, monkeypatch):
    from configurator.handlers import MISSING_DEPENDENCY
    if MISSING_DEPENDENCY:
        pytest.skip(f"configurator.handlers could not import {MISSING_DEPENDENCY!r}")
    from configurator import server as server_mod
    srv = server_mod.ConfigAPIServer()
    srv.app.config["TESTING"] = True
    monkeypatch.setattr(srv.configdb, "clear_all", lambda: True)
    monkeypatch.setattr(srv.systemd_handler, "reset_managed_services", lambda: {})
    monkeypatch.setattr(server_mod, "reset_pipewire_settings",
                        lambda: {"status": "unavailable"})
    seen = []
    monkeypatch.setattr(server_mod.audio_server, "reset",
                        lambda pipewire_reached: seen.append(pipewire_reached)
                        or {"status": "success", "reboot_required": False})
    with srv.app.test_client() as c:
        r = c.post("/api/v1/config/reset")
    assert r.status_code == 200
    assert r.get_json()["data"]["audio_server"] == {
        "status": "success", "reboot_required": False}
    assert seen == [False]
