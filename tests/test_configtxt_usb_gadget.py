import pytest

from configurator.configtxt import ConfigTxt, UnsupportedModelError


class FakeModel:
    def __init__(self, version, supported=True):
        self._version = version
        self._supported = supported

    def get_version(self):
        return self._version

    def get_model_name(self):
        return f"Fake {self._version}"

    def supports_usb_gadget(self):
        return self._supported


CM5_SAMPLE = """\
[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=i2c_arm=on
"""

CM4_SAMPLE = """\
[cm4]
otg_mode=1

[all]
dtparam=i2c_arm=on
"""


def _cfg(tmp_path, content):
    p = tmp_path / "config.txt"
    p.write_text(content)
    return ConfigTxt(file_path=str(p))


def test_cm5_host_line_is_flipped_to_peripheral(tmp_path):
    cfg = _cfg(tmp_path, CM5_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    text = "".join(cfg.lines)
    assert "dr_mode=peripheral" in text
    assert "dr_mode=host" not in text


def test_cm4_otg_mode_is_removed(tmp_path):
    cfg = _cfg(tmp_path, CM4_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM4"))
    text = "".join(cfg.lines)
    assert "otg_mode=1" not in text
    assert "dtoverlay=dwc2,dr_mode=peripheral" in text


def test_enable_is_idempotent(tmp_path):
    cfg = _cfg(tmp_path, CM5_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    first = "".join(cfg.lines)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    assert "".join(cfg.lines) == first


def test_unsupported_model_raises(tmp_path):
    cfg = _cfg(tmp_path, CM5_SAMPLE)
    with pytest.raises(UnsupportedModelError):
        cfg.enable_usb_gadget(pi_model=FakeModel("2", supported=False))


def test_disable_restores_host_mode(tmp_path):
    cfg = _cfg(tmp_path, CM5_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    cfg.disable_usb_gadget(pi_model=FakeModel("CM5"))
    text = "".join(cfg.lines)
    assert "dr_mode=host" in text
    assert "dr_mode=peripheral" not in text


def test_default_config_does_not_clobber_gadget_setting(tmp_path):
    """--default-config must not undo USB gadget mode."""
    cfg = _cfg(tmp_path, CM5_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    cfg.default_config()
    assert "dr_mode=peripheral" in "".join(cfg.lines)
