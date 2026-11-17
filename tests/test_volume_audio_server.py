"""Under aas, config-volume leaves the default ctl's Master and Capture alone."""

import pytest

from configurator import audio_server, volume


class FakeDB:
    data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeCard:
    def get_mixer_control_name(self, use_softvol_fallback=False):
        return "Digital"


@pytest.fixture
def env(monkeypatch):
    calls = {"card_set": [], "pw_available": 0, "pw_get": [], "pw_set": []}
    FakeDB.data = {
        volume.VOLUME_DB_KEY: 40,
        volume.VOLUME_CARD_DB_KEY: "0",
        volume.VOLUME_CONTROL_DB_KEY: "Digital",
        volume.PIPEWIRE_MASTER_VOLUME_KEY: 55,
        volume.PIPEWIRE_CAPTURE_VOLUME_KEY: 66,
    }
    monkeypatch.setattr(volume, "ConfigDB", FakeDB)
    monkeypatch.setattr(volume, "get_cached_card_index", lambda: 0)
    monkeypatch.setattr(volume, "_cached_soundcard", FakeCard())
    monkeypatch.setattr(volume, "get_current_volume", lambda c, n: 41)

    def card_set(c, n, v):
        calls["card_set"].append(v)
        return True

    def available():
        calls["pw_available"] += 1
        return True

    def pw_get(name):
        calls["pw_get"].append(name)
        return 77

    def pw_set(name, v):
        calls["pw_set"].append((name, v))
        return True

    monkeypatch.setattr(volume, "set_volume", card_set)
    monkeypatch.setattr(volume, "store_headphone_volume", lambda: False)
    monkeypatch.setattr(volume, "restore_headphone_volume", lambda: False)
    monkeypatch.setattr(volume, "is_pipewire_available", available)
    monkeypatch.setattr(volume, "get_pipewire_volume", pw_get)
    monkeypatch.setattr(volume, "set_pipewire_volume", pw_set)
    return calls


def test_store_under_aas_skips_pipewire(env, monkeypatch):
    monkeypatch.setattr(audio_server, "chosen", lambda: "aas")
    assert volume.store_volume() is True
    assert FakeDB.data[volume.VOLUME_DB_KEY] == 41
    assert FakeDB.data[volume.PIPEWIRE_MASTER_VOLUME_KEY] == 55
    assert env["pw_available"] == 0
    assert env["pw_get"] == []


def test_restore_under_aas_skips_pipewire(env, monkeypatch):
    monkeypatch.setattr(audio_server, "chosen", lambda: "aas")
    assert volume.restore_volume() is True
    assert env["card_set"] == [40]
    assert env["pw_available"] == 0
    assert env["pw_set"] == []


def test_store_under_pipewire_as_before(env, monkeypatch):
    monkeypatch.setattr(audio_server, "chosen", lambda: "pipewire")
    assert volume.store_volume() is True
    assert FakeDB.data[volume.PIPEWIRE_MASTER_VOLUME_KEY] == 77
    assert FakeDB.data[volume.PIPEWIRE_CAPTURE_VOLUME_KEY] == 77
    assert env["pw_get"] == ["Master", "Capture"]


def test_restore_under_pipewire_as_before(env, monkeypatch):
    monkeypatch.setattr(audio_server, "chosen", lambda: "pipewire")
    assert volume.restore_volume() is True
    assert env["card_set"] == [40]
    assert env["pw_set"] == [("Master", 55), ("Capture", 66)]
