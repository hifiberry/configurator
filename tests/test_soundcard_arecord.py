from unittest.mock import patch
from pathlib import Path
from typing import Any

from src.soundcard import SOUND_CARD_DEFINITIONS  # type: ignore[import-untyped]
from src.soundcard_detector import SoundcardDetector


ARECORD_ADC = """**** List of CAPTURE Hardware Devices ****
card 2: sndrpihifiberry [snd_rpi_hifiberry_adc], device 0: HiFiBerry ADC HiFi pcm1863-aif-0 [HiFiBerry ADC HiFi pcm1863-aif-0]
  Subdevices: 0/1
  Subdevice #0: subdevice #0
"""

ARECORD_NO_HIFIBERRY = """**** List of CAPTURE Hardware Devices ****
card 0: Generic [HD-Audio Generic], device 0: ALC generic [ALC generic]
  Subdevices: 1/1
"""


def _detector(tmp_path: Path) -> Any:
    cfg = tmp_path / "config.txt"
    cfg.write_text("dtoverlay=hifiberry-adc\n")
    return SoundcardDetector(config_file=str(cfg))


def test_adc_entry_has_arecord_marker():
    assert SOUND_CARD_DEFINITIONS["ADC"]["arecord_contains"] == "snd_rpi_hifiberry_adc"


def test_detect_from_arecord_finds_adc(tmp_path: Path) -> None:
    det = _detector(tmp_path)
    with patch.object(det, "_run_command", return_value=ARECORD_ADC):
        assert det._detect_from_arecord() == "adc"


def test_detect_from_arecord_none_when_no_hifiberry_input(tmp_path: Path) -> None:
    det = _detector(tmp_path)
    with patch.object(det, "_run_command", return_value=ARECORD_NO_HIFIBERRY):
        assert det._detect_from_arecord() is None


def test_detect_from_arecord_none_when_no_capture_devices(tmp_path: Path) -> None:
    det = _detector(tmp_path)
    with patch.object(det, "_run_command", return_value=""):
        assert det._detect_from_arecord() is None
