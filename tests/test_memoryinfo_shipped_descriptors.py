import os
from configurator.memoryinfo import load_descriptors

FEATURES_D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "features.d")


def test_every_shipped_descriptor_loads():
    descriptors = load_descriptors([FEATURES_D])
    assert len(descriptors) == len(os.listdir(FEATURES_D))


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
