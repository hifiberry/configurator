"""DSP-checksum refinement: which cards it may re-label, and which it must not.

The refinement exists to tell boards apart whose DSP *is* the card: a
Beocreate 4-Channel Amplifier and a DAC+ DSP are told apart only by the
program their DSP runs.  A card that merely hosts a DSP add-on (Digi2 Pro,
DAC2 Pro, ...) is a different product whatever program the add-on runs, so
the checksum says nothing about it.  hifiberry-os#665: a Digi2 Pro with a DSP
add-on that had the DAC+ DSP profile installed was re-labelled "DAC+ DSP",
overriding the card the user had pinned, and the volume control moved to
DSPVolume.
"""

import io
import json
import urllib.request

import pytest

from configurator.soundcard import SOUND_CARD_DEFINITIONS
from configurator.soundcard_detector import (
    KNOWN_DSP_CHECKSUM_TO_CARD,
    SoundcardDetector,
)

DACDSP_15_SHA1 = "73EA5CD7BE4DB20510DB6B6BE974103046AEBD50"
BEOCREATE_FACTORY_SHA1 = next(iter(KNOWN_DSP_CHECKSUM_TO_CARD))


def _serve_checksum(monkeypatch, sha1, calls=None):
    def fake_urlopen(url, timeout=None):
        if calls is not None:
            calls.append(url)
        body = json.dumps({"length": {"sha1": sha1}}).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _profile(tmp_path, name, sha1, model):
    (tmp_path / name).write_text(
        "<ROM>\n"
        f'  <metadata type="checksum_sha1">{sha1}</metadata>\n'
        f'  <metadata type="modelName">{model}</metadata>\n'
        "</ROM>\n"
    )


def _detector(tmp_path, card):
    cfg = tmp_path / "config.txt"
    cfg.write_text("")
    det = SoundcardDetector(config_file=str(cfg))
    det.DSP_PROFILE_DIR = str(tmp_path)
    det.detected_card = card
    return det


def test_digi2_pro_with_dacdsp_program_on_addon_is_not_relabelled(tmp_path, monkeypatch):
    _profile(tmp_path, "dacdsp-15.xml", DACDSP_15_SHA1, "DAC+ DSP")
    calls = []
    _serve_checksum(monkeypatch, DACDSP_15_SHA1, calls)
    det = _detector(tmp_path, "Digi2 Pro")

    det._refine_card_by_dsp_program()

    assert det.detected_card == "Digi2 Pro"
    assert calls == []          # not even asked: the checksum cannot apply


@pytest.mark.parametrize("card", ["DAC2 Pro", "Amp4 Pro", "Digi+ Pro", "Amp100"])
def test_addon_hosts_are_never_relabelled(tmp_path, monkeypatch, card):
    _profile(tmp_path, "dacdsp-15.xml", DACDSP_15_SHA1, "DAC+ DSP")
    _serve_checksum(monkeypatch, DACDSP_15_SHA1)
    det = _detector(tmp_path, card)

    det._refine_card_by_dsp_program()

    assert det.detected_card == card


def test_dacdsp_running_beocreate_factory_firmware_becomes_beocreate(tmp_path, monkeypatch):
    _serve_checksum(monkeypatch, BEOCREATE_FACTORY_SHA1)
    det = _detector(tmp_path, "DAC+ DSP")

    det._refine_card_by_dsp_program()

    assert det.detected_card == "Beocreate 4-Channel Amplifier"


def test_dacdsp_running_beocreate_profile_becomes_beocreate(tmp_path, monkeypatch):
    sha1 = "E9C0BF069CC96EA37EDF7E8DEC0720F969EE0D66"
    _profile(tmp_path, "beocreate-universal-11.xml", sha1,
             "Beocreate 4-Channel Amplifier")
    _serve_checksum(monkeypatch, sha1)
    det = _detector(tmp_path, "DAC+ DSP")

    det._refine_card_by_dsp_program()

    assert det.detected_card == "Beocreate 4-Channel Amplifier"


def test_beocreate_running_dacdsp_profile_becomes_dacdsp(tmp_path, monkeypatch):
    _profile(tmp_path, "dacdsp-15.xml", DACDSP_15_SHA1, "DAC+ DSP")
    _serve_checksum(monkeypatch, DACDSP_15_SHA1)
    det = _detector(tmp_path, "Beocreate 4-Channel Amplifier")

    det._refine_card_by_dsp_program()

    assert det.detected_card == "DAC+ DSP"


def test_amp100_hosts_a_dsp_addon():
    # The Amp100 takes the DSP add-on; it was listed as not supporting DSP.
    assert SOUND_CARD_DEFINITIONS["Amp100"]["supports_dsp"] is True
