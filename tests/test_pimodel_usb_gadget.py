from unittest.mock import mock_open, patch

from configurator.pimodel import PiModel, USB_GADGET_SUPPORT


def _model(model_string):
    with patch("builtins.open", mock_open(read_data=model_string)):
        return PiModel()


def test_cm5_is_distinct_from_pi5():
    assert _model("Raspberry Pi Compute Module 5 Lite Rev 1.0").get_version() == "CM5"
    assert _model("Raspberry Pi 5 Model B Rev 1.0").get_version() == "5"


def test_cm5_and_pi5_both_support_gadget_on_usb_c():
    assert _model("Raspberry Pi Compute Module 5 Lite Rev 1.0").supports_usb_gadget() is True
    assert _model("Raspberry Pi 5 Model B Rev 1.0").supports_usb_gadget() is True
    assert _model("Raspberry Pi 5 Model B Rev 1.0").usb_gadget_port() == "USB-C"


def test_pi4_and_cm4_support_gadget():
    assert _model("Raspberry Pi 4 Model B Rev 1.4").supports_usb_gadget() is True
    assert _model("Raspberry Pi 4 Model B Rev 1.4").usb_gadget_port() == "USB-C"
    assert _model("Raspberry Pi Compute Module 4 Rev 1.0").supports_usb_gadget() is True
    assert _model("Raspberry Pi Compute Module 4 Rev 1.0").usb_gadget_port() == "micro-USB"


def test_pi2_does_not_support_gadget():
    pi2 = _model("Raspberry Pi 2 Model B Rev 1.1")
    assert pi2.supports_usb_gadget() is False
    assert pi2.usb_gadget_port() is None


def test_unknown_model_does_not_support_gadget():
    assert _model("Some Other Board").supports_usb_gadget() is False


def test_support_table_covers_every_known_version():
    for version in ("0W", "02W", "3A+", "3B", "3B+", "4", "CM4", "5", "CM5", "2"):
        assert version in USB_GADGET_SUPPORT
