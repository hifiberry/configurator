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

# Realistic multi-section config.txt as shipped on real hardware: every
# model's section is present at once (that's the whole point of conditional
# sections -- one image boots many boards). The stock dwc2 line lives only
# under [cm5]; other models have no dwc2 line anywhere.
REALISTIC_SAMPLE = """\
dtparam=audio=off
dtoverlay=vc4-kms-v3d,noaudio

[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[pi5]
dtoverlay=nospi10

[all]
dtparam=i2c_arm=on
force_eeprom_read=1
dtparam=spi=on
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


# --- Realistic multi-section fixture: every model section present at once ---


def test_pi5_gadget_mode_does_not_write_into_inert_cm5_section(tmp_path):
    """On a real Pi 5, the stock [cm5] dtoverlay=dwc2 line is inert (a Pi 5
    never reads [cm5]). enable_usb_gadget must apply peripheral mode where a
    Pi 5 actually reads it ([all]), not silently edit the dead [cm5] line."""
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("5"))
    text = "".join(cfg.lines)

    # The inert [cm5] host line must remain untouched.
    cm5_block = text.split("[cm5]")[1].split("[pi5]")[0]
    assert "dtoverlay=dwc2,dr_mode=host" in cm5_block
    assert "peripheral" not in cm5_block

    # The peripheral line must have landed in [all], which a Pi 5 does read.
    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2,dr_mode=peripheral" in all_block


def test_pi5_gadget_mode_idempotent_on_realistic_fixture(tmp_path):
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("5"))
    first = "".join(cfg.lines)
    cfg.enable_usb_gadget(pi_model=FakeModel("5"))
    assert "".join(cfg.lines) == first


def test_cm5_gadget_mode_updates_stock_line_in_place_on_realistic_fixture(tmp_path):
    """CM5's stock [cm5] dwc2 line must be edited in place, and no duplicate
    dwc2 line should be added to [all]."""
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    text = "".join(cfg.lines)

    cm5_block = text.split("[cm5]")[1].split("[pi5]")[0]
    assert "dtoverlay=dwc2,dr_mode=peripheral" in cm5_block

    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2" not in all_block


def test_cm5_gadget_mode_idempotent_on_realistic_fixture(tmp_path):
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    first = "".join(cfg.lines)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM5"))
    assert "".join(cfg.lines) == first


def test_cm4_gadget_mode_removes_otg_mode_and_restores_on_disable(tmp_path):
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM4"))
    text = "".join(cfg.lines)
    assert "otg_mode=1" not in text
    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2,dr_mode=peripheral" in all_block

    cfg.disable_usb_gadget(pi_model=FakeModel("CM4"))
    text = "".join(cfg.lines)
    cm4_block = text.split("[cm4]")[1].split("[cm5]")[0]
    assert "otg_mode=1" in cm4_block
    # The dwc2 line enable added to [all] must be cleaned back up, not left
    # behind pointing at host mode.
    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2" not in all_block


def test_cm4_gadget_mode_idempotent_on_realistic_fixture(tmp_path):
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM4"))
    first = "".join(cfg.lines)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM4"))
    assert "".join(cfg.lines) == first


def test_cm4_disable_restores_otg_mode_true_round_trip(tmp_path):
    """enable -> disable on CM4 must restore otg_mode=1, not silently drop
    the board to dwc2's slower built-in host mode forever."""
    cfg = _cfg(tmp_path, CM4_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("CM4"))
    cfg.disable_usb_gadget(pi_model=FakeModel("CM4"))
    text = "".join(cfg.lines)
    assert "otg_mode=1" in text


def test_pi5_enable_does_not_remove_cm4_otg_mode(tmp_path):
    """A real config.txt carries every model's section at once. Enabling
    gadget mode on a Pi 5 must not touch [cm4] otg_mode=1: a Pi 5 never
    reads [cm4], and if this card is later moved into a CM4, otg_mode=1
    must still be there to select the stock XHCI host controller instead
    of silently falling back to dwc2's slower built-in host mode."""
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("5"))
    text = "".join(cfg.lines)
    cm4_block = text.split("[cm4]")[1].split("[cm5]")[0]
    assert "otg_mode=1" in cm4_block


def test_pi5_disable_removes_added_all_section_line(tmp_path):
    """On Pi 5, disable must remove the dwc2 line enable added to [all]
    rather than leaving a host-mode line that was never there before."""
    cfg = _cfg(tmp_path, REALISTIC_SAMPLE)
    cfg.enable_usb_gadget(pi_model=FakeModel("5"))
    cfg.disable_usb_gadget(pi_model=FakeModel("5"))
    text = "".join(cfg.lines)
    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2" not in all_block
    # And the inert [cm5] line should still be exactly what it started as.
    cm5_block = text.split("[cm5]")[1].split("[pi5]")[0]
    assert "dtoverlay=dwc2,dr_mode=host" in cm5_block
