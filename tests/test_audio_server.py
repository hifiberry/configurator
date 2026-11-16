"""Reading and setting the audio server (PipeWire or aas)."""

import subprocess

import pytest

from configurator import audio_server


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def paths(tmp_path, monkeypatch):
    choice = tmp_path / "audio-server"
    command = tmp_path / "hifiberry-audio-server"
    monkeypatch.setattr(audio_server, "CHOICE_PATH", str(choice))
    monkeypatch.setattr(audio_server, "COMMAND", str(command))
    return choice, command


def install(command):
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)


@pytest.mark.parametrize("content,expected", [
    (None, "pipewire"),
    ("aas\n", "aas"),
    ("aas  ", "aas"),
    ("", "pipewire"),
    ("foo\n", "pipewire"),
    ("pipewire\n", "pipewire"),
])
def test_chosen(paths, content, expected):
    choice, _ = paths
    if content is not None:
        choice.write_text(content)
    assert audio_server.chosen() == expected


def fake_run(monkeypatch, running="pipewire", set_result=None, calls=None):
    def run(cmd, **kwargs):
        assert isinstance(cmd, list)
        assert not kwargs.get("shell")
        assert kwargs.get("timeout") == 30
        if calls is not None:
            calls.append(cmd)
        if cmd[1] == "get":
            return Completed(0, f"running {running}\nchosen x\n")
        return set_result or Completed(0, "chosen\n")
    monkeypatch.setattr(subprocess, "run", run)


def test_get_without_command(paths, monkeypatch):
    choice, _ = paths
    choice.write_text("aas\n")
    calls = []
    fake_run(monkeypatch, calls=calls)
    assert audio_server.get() == {
        "running": "pipewire", "chosen": "aas", "available": False}
    assert calls == []


def test_get_with_command(paths, monkeypatch):
    choice, command = paths
    install(command)
    choice.write_text("aas\n")
    fake_run(monkeypatch, running="aas")
    assert audio_server.get() == {
        "running": "aas", "chosen": "aas", "available": True}


def test_set_bad_name(paths, monkeypatch):
    install(paths[1])
    with pytest.raises(ValueError):
        audio_server.set_server("jack")


def test_set_unavailable(paths):
    with pytest.raises(audio_server.AudioServerUnavailable):
        audio_server.set_server("aas")


def test_set_failure_carries_stderr(paths, monkeypatch):
    install(paths[1])
    fake_run(monkeypatch, set_result=Completed(1, "", "needs root\n"))
    with pytest.raises(audio_server.AudioServerError, match="needs root"):
        audio_server.set_server("aas")


@pytest.mark.parametrize("running,server,reboot", [
    ("pipewire", "aas", True),
    ("pipewire", "pipewire", False),
])
def test_set_success(paths, monkeypatch, running, server, reboot):
    choice, command = paths
    install(command)

    def run(cmd, **kwargs):
        if cmd[1] == "set":
            choice.write_text(cmd[2] + "\n")
            return Completed(0, "chosen\n")
        return Completed(0, f"running {running}\nchosen x\n")
    monkeypatch.setattr(subprocess, "run", run)
    data = audio_server.set_server(server)
    assert data == {"running": running, "chosen": server,
                    "available": True, "reboot_required": reboot}


# --- routes -----------------------------------------------------------------

def _server_class():
    pytest.importorskip("flask", reason="Flask is absent in the build chroot")
    from configurator.handlers import MISSING_DEPENDENCY
    if MISSING_DEPENDENCY:
        pytest.skip(f"configurator.handlers could not import {MISSING_DEPENDENCY!r}")
    from configurator.server import ConfigAPIServer
    return ConfigAPIServer


@pytest.fixture
def client():
    srv = _server_class()()
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        yield c


def test_route_get_without_command(paths, client, monkeypatch):
    fake_run(monkeypatch)
    r = client.get("/api/v1/audio-server")
    assert r.status_code == 200
    assert r.get_json() == {"status": "success", "data": {
        "running": "pipewire", "chosen": "pipewire", "available": False}}


@pytest.mark.parametrize("body", [{"server": "jack"}, {}, {"server": 3}])
def test_route_post_bad_body(paths, client, body):
    r = client.post("/api/v1/audio-server", json=body)
    assert r.status_code == 400
    assert r.get_json()["status"] == "error"


def test_route_post_not_json(paths, client):
    r = client.post("/api/v1/audio-server", data="aas")
    assert r.status_code == 400


def test_route_post_unavailable(paths, client):
    r = client.post("/api/v1/audio-server", json={"server": "aas"})
    assert r.status_code == 409
    assert "not installed" in r.get_json()["message"]


def test_route_post_failure(paths, client, monkeypatch):
    install(paths[1])
    fake_run(monkeypatch, set_result=Completed(1, "", "boom"))
    r = client.post("/api/v1/audio-server", json={"server": "aas"})
    assert r.status_code == 500
    assert "boom" in r.get_json()["message"]


def test_route_post_success(paths, client, monkeypatch):
    choice, command = paths
    install(command)

    def run(cmd, **kwargs):
        if cmd[1] == "set":
            choice.write_text("aas\n")
            return Completed(0)
        return Completed(0, "running pipewire\nchosen pipewire\n")
    monkeypatch.setattr(subprocess, "run", run)
    r = client.post("/api/v1/audio-server", json={"server": "aas"})
    assert r.status_code == 200
    assert r.get_json() == {"status": "success", "data": {
        "running": "pipewire", "chosen": "aas", "available": True,
        "reboot_required": True}}
