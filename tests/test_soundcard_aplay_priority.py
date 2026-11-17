"""aplay-priority detection when one overlay belongs to several cards.

DAC+ ADC Pro and DAC2 ADC Pro both load hifiberry-dacplusadcpro, so the
overlay aplay reports maps to the joined name "DAC+ ADC Pro/DAC2 ADC Pro".
That used to match nothing in SOUND_CARD_DEFINITIONS and fall back to the
standard detection, whose I2C probe (it only works as root) answered
"DAC+/Amp2": a card with a different overlay and no ADC.
"""

from unittest.mock import patch

from configurator import soundcard as sc
from configurator import soundcard_detector as sd
from configurator.soundcard import Soundcard
from configurator.soundcard_detector import SoundcardDetector

APLAY_ADCPRO = (
    "**** List of PLAYBACK Hardware Devices ****\n"
    "card 0: sndrpihifiberry [snd_rpi_hifiberry_dacplusadcpro], device 0: "
    "HiFiBerry DAC+ADC Pro HiFi pcm512x-hifi-0 [HiFiBerry DAC+ADC Pro HiFi pcm512x-hifi-0]\n"
)
APLAY_AMP4PRO = APLAY_ADCPRO.replace("dacplusadcpro", "amp4pro")
APLAY_NONE = (
    "**** List of PLAYBACK Hardware Devices ****\n"
    "card 0: Generic [HD-Audio Generic], device 0: ALC generic [ALC generic]\n"
)


def _detect(aplay, i2c_card, hat_product=None, standard=None):
    """Run aplay-priority detection with every hardware source faked."""

    def fake_detect_card(self, ignore_pin=False):
        self.detected_card = i2c_card

    hat = {"product": hat_product} if hat_product else {}
    with patch.object(sc.subprocess, "check_output", return_value=aplay), \
            patch.object(sd, "ConfigTxt", lambda *a, **k: None), \
            patch.object(SoundcardDetector, "detect_from_config_txt_comment",
                         return_value=None), \
            patch.object(SoundcardDetector, "detect_card", fake_detect_card), \
            patch.object(sc, "get_hat_info", return_value=hat), \
            patch.object(Soundcard, "_detect_card", return_value=standard) as fallback:
        card = Soundcard(prioritize_aplay=True)
    return card, fallback


def test_shared_overlay_ignores_i2c_guess_with_other_overlay():
    card, fallback = _detect(APLAY_ADCPRO, i2c_card="DAC+/Amp2")
    assert card.name == "DAC+ ADC Pro"
    assert card.input_channels == 2
    fallback.assert_not_called()


def test_shared_overlay_takes_candidate_named_by_other_evidence():
    card, fallback = _detect(APLAY_ADCPRO, i2c_card="DAC2 ADC Pro")
    assert card.name == "DAC2 ADC Pro"
    assert card.supports_dsp is True
    fallback.assert_not_called()


def test_shared_overlay_takes_candidate_named_by_hat_product():
    card, _ = _detect(APLAY_ADCPRO, i2c_card="DAC+/Amp2", hat_product="DAC2 ADC Pro")
    assert card.name == "DAC2 ADC Pro"


def test_unambiguous_overlay_is_unchanged():
    cards = [n for n, d in sc.SOUND_CARD_DEFINITIONS.items()
             if d.get("dtoverlay") == "hifiberry-amp4pro"]
    assert len(cards) == 1
    card, fallback = _detect(APLAY_AMP4PRO, i2c_card="DAC+/Amp2")
    assert card.name == cards[0]
    fallback.assert_not_called()


def test_no_aplay_card_falls_back_to_standard_detection():
    standard = {"name": "DAC+ ADC", **sc.SOUND_CARD_DEFINITIONS["DAC+ ADC"]}
    card, fallback = _detect(APLAY_NONE, i2c_card="DAC+/Amp2", standard=standard)
    assert card.name == "DAC+ ADC"
    fallback.assert_called_once()
