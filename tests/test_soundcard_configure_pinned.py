import logging

from configurator.soundcard_detector import SoundcardDetector


def _detector(tmp_path):
    cfg = tmp_path / "config.txt"
    cfg.write_text("# HiFiBerry card: Beocreate 4-Channel Amplifier\n"
                   "dtoverlay=hifiberry-dac\n")
    return SoundcardDetector(config_file=str(cfg))


def _errors(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


def test_configure_card_no_error_when_card_pinned_without_overlay(tmp_path, caplog):
    """A pinned card is a successful detection, not a failed one.

    detect_card() Step 0 (ConfigDB) and Step 0b (config.txt comment) both set
    detected_card and deliberately leave detected_overlay as None. configure_card()
    must not report that as "no sound card detected".
    """
    det = _detector(tmp_path)
    det.detected_card = "Beocreate 4-Channel Amplifier"
    det.detected_overlay = None

    with caplog.at_level(logging.DEBUG):
        det.configure_card()

    assert _errors(caplog) == []


def test_configure_card_errors_when_nothing_detected(tmp_path, caplog):
    """The genuine no-card case must still report an error."""
    det = _detector(tmp_path)
    det.detected_card = None
    det.detected_overlay = None

    with caplog.at_level(logging.DEBUG):
        det.configure_card()

    assert any("No sound card detected" in m for m in _errors(caplog))
