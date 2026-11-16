import json
import os

import pytest

from configurator import audio_server
from configurator.memoryinfo import load_descriptors

FEATURES_D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "features.d")


@pytest.fixture(autouse=True)
def pipewire_chosen(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_server, "CHOICE_PATH", str(tmp_path / "audio-server"))


def _choose(server):
    with open(audio_server.CHOICE_PATH, "w") as f:
        f.write(server + "\n")


def test_every_shipped_descriptor_loads():
    # aas and pipewire are alternatives: one of the two is always loaded.
    descriptors = load_descriptors([FEATURES_D])
    assert len(descriptors) == len(os.listdir(FEATURES_D)) - 1


@pytest.mark.parametrize("server,other", [("pipewire", "aas"), ("aas", "pipewire")])
def test_audio_engine_follows_the_chosen_server(server, other):
    _choose(server)
    ids = {d.id for d in load_descriptors([FEATURES_D])}
    assert server in ids
    assert other not in ids


def test_unreadable_choice_means_pipewire():
    ids = {d.id for d in load_descriptors([FEATURES_D])}
    assert "pipewire" in ids and "aas" not in ids


def test_descriptor_without_audio_server_is_always_loaded(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.json").write_text(json.dumps({"systemd_services": ["x.service"]}))
    for server in ("pipewire", "aas"):
        _choose(server)
        assert [f.id for f in load_descriptors([str(d)])] == ["x"]


def test_infrastructure_is_marked_required():
    by_id = {d.id: d for d in load_descriptors([FEATURES_D])}
    for feature_id in ("audiocontrol", "pipewire", "configurator", "webui"):
        assert by_id[feature_id].disposition == "required", feature_id


def test_mpd_is_disable_not_uninstall():
    # mpd is in hbos-minimal's Depends, so apt remove would take the
    # meta-package with it. systemctl disable is the only correct advice.
    by_id = {d.id: d for d in load_descriptors([FEATURES_D])}
    assert by_id["mpd"].disposition == "disable"


def test_display_claims_the_browser_by_process():
    by_id = {d.id: d for d in load_descriptors([FEATURES_D])}
    assert "cog" in by_id["display"].processes
    assert "cage" in by_id["display"].processes


def test_audiocontrol_claims_its_metadata_service_too():
    # audiocontrol.service and audiocontrol-metadata.service are separate
    # systemd units but one feature -- the metadata half shouldn't derive
    # into its own "none" disposition row.
    by_id = {d.id: d for d in load_descriptors([FEATURES_D])}
    assert "audiocontrol.service" in by_id["audiocontrol"].units
    assert "audiocontrol-metadata.service" in by_id["audiocontrol"].units
