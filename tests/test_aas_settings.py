"""Reading and setting aas's card latency in aas.local.toml."""

import tomllib

import pytest

from configurator import aas_settings


@pytest.fixture
def local(tmp_path, monkeypatch):
    path = tmp_path / "aas" / "aas.local.toml"
    path.parent.mkdir()
    monkeypatch.setattr(aas_settings, "LOCAL_PATH", str(path))
    return path


@pytest.fixture
def restarts(monkeypatch):
    class Restarts(list):
        state = {"active": True}

    calls = Restarts()
    monkeypatch.setattr(aas_settings, "_aas_active", lambda: calls.state["active"])
    monkeypatch.setattr(aas_settings, "_restart", lambda: calls.append("restart"))
    return calls


def test_get_without_file(local):
    assert aas_settings.get() == {"latency_ms": None}


def test_get_reads_top_level_key(local):
    local.write_text("latency_ms = 8\n[aes67]\nlatency_ms = 3\n")
    assert aas_settings.get() == {"latency_ms": 8}


def test_post_writes_and_restarts(local, restarts):
    assert aas_settings.set_latency(6) == {"latency_ms": 6, "restarted": True}
    assert tomllib.loads(local.read_text())["latency_ms"] == 6
    assert restarts == ["restart"]


def test_post_creates_directory(tmp_path, monkeypatch, restarts):
    path = tmp_path / "new" / "aas.local.toml"
    monkeypatch.setattr(aas_settings, "LOCAL_PATH", str(path))
    aas_settings.set_latency(5)
    assert tomllib.loads(path.read_text())["latency_ms"] == 5


def test_post_null_removes_key(local, restarts):
    local.write_text('bit_perfect = "off"\nlatency_ms = 8\n[aes67]\nlatency_ms = 3\n')
    assert aas_settings.set_latency(None) == {"latency_ms": None, "restarted": True}
    data = tomllib.loads(local.read_text())
    assert "latency_ms" not in data
    assert data["bit_perfect"] == "off"
    assert data["aes67"]["latency_ms"] == 3


def test_post_keeps_other_lines(local, restarts):
    local.write_text('# mine\n\nbit_perfect = "off"\nlatency_ms = 12\n\n'
                     '[aes67]\ninterface = "eth0"  # wired\n')
    aas_settings.set_latency(6)
    after = local.read_text().splitlines()
    before = ['# mine', '', 'bit_perfect = "off"', 'latency_ms = 12', '',
              '[aes67]', 'interface = "eth0"  # wired']
    assert [l for l in after if l != "latency_ms = 6"] == [
        l for l in before if l != "latency_ms = 12"]
    assert tomllib.loads(local.read_text())["latency_ms"] == 6


def test_post_into_file_with_only_tables(local, restarts):
    local.write_text('[aes67]\nptp = "listen"\n')
    aas_settings.set_latency(4)
    data = tomllib.loads(local.read_text())
    assert data["latency_ms"] == 4
    assert data["aes67"]["ptp"] == "listen"


def test_post_refuses_invalid_file(local, restarts):
    local.write_text("latency_ms = = 4")
    with pytest.raises(aas_settings.AasSettingsFileError):
        aas_settings.set_latency(6)
    assert local.read_text() == "latency_ms = = 4"
    assert restarts == []


@pytest.mark.parametrize("bad", [0, 101, 4.5, "6", True])
def test_post_refuses_bad_values(local, bad):
    local.write_text("latency_ms = 7\n")
    with pytest.raises(ValueError):
        aas_settings.set_latency(bad)
    assert local.read_text() == "latency_ms = 7\n"


def test_no_restart_when_aas_is_not_active(local, restarts):
    restarts.state["active"] = False
    assert aas_settings.set_latency(6) == {"latency_ms": 6, "restarted": False}
    assert restarts == []


# --- routes -----------------------------------------------------------------

@pytest.fixture
def client():
    pytest.importorskip("flask", reason="Flask is absent in the build chroot")
    from configurator.handlers import MISSING_DEPENDENCY
    if MISSING_DEPENDENCY:
        pytest.skip(f"configurator.handlers could not import {MISSING_DEPENDENCY!r}")
    from configurator.server import ConfigAPIServer
    srv = ConfigAPIServer()
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        yield c


def test_routes(local, restarts, client):
    r = client.get("/api/v1/audio-server/aas-settings")
    assert r.status_code == 200
    assert r.get_json() == {"status": "success", "data": {"latency_ms": None}}

    r = client.post("/api/v1/audio-server/aas-settings", json={"latency_ms": 9})
    assert r.status_code == 200
    assert r.get_json()["data"] == {"latency_ms": 9, "restarted": True}

    r = client.post("/api/v1/audio-server/aas-settings", json={"latency_ms": 0})
    assert r.status_code == 400
    r = client.post("/api/v1/audio-server/aas-settings", json={})
    assert r.status_code == 400

    local.write_text("latency_ms = = 4")
    r = client.post("/api/v1/audio-server/aas-settings", json={"latency_ms": 6})
    assert r.status_code == 409
