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
    assert audio_server.reset() == {"status": "unavailable"}
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
    assert not state.exists()
    assert ("systemctl", "start", "aas.service") in calls
    assert ("set", "pipewire") in calls


def test_failing_set_reported(env, monkeypatch):
    command, state = env
    install(command)
    fake_run(monkeypatch, state, active=False, fail={("set", "pipewire")})
    result = audio_server.reset()
    assert result["status"] == "error"
    assert "boom" in result["message"]


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
    monkeypatch.setattr(server_mod.audio_server, "reset",
                        lambda: {"status": "success"})
    with srv.app.test_client() as c:
        r = c.post("/api/v1/config/reset")
    assert r.status_code == 200
    assert r.get_json()["data"]["audio_server"] == {"status": "success"}
