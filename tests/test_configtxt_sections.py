from configurator.configtxt import ConfigTxt

SAMPLE = """\
dtparam=audio=off

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=i2c_arm=on
"""


def _cfg(tmp_path, content=SAMPLE):
    p = tmp_path / "config.txt"
    p.write_text(content)
    return ConfigTxt(file_path=str(p))


def test_update_replaces_line_within_its_own_section(tmp_path):
    cfg = _cfg(tmp_path)
    cfg._update_line_in_section("cm5", "dtoverlay=dwc2", "dtoverlay=dwc2,dr_mode=peripheral\n")
    text = "".join(cfg.lines)
    assert "dtoverlay=dwc2,dr_mode=peripheral" in text
    assert "dr_mode=host" not in text
    # the replacement must stay inside [cm5], not drift into [all]
    cm5_block = text.split("[cm5]")[1].split("[all]")[0]
    assert "dr_mode=peripheral" in cm5_block


def test_update_inserts_into_existing_section_when_absent(tmp_path):
    cfg = _cfg(tmp_path)
    cfg._update_line_in_section("all", "dtoverlay=dwc2", "dtoverlay=dwc2,dr_mode=peripheral\n")
    text = "".join(cfg.lines)
    all_block = text.split("[all]")[1]
    assert "dtoverlay=dwc2,dr_mode=peripheral" in all_block


def test_update_creates_section_when_missing(tmp_path):
    cfg = _cfg(tmp_path, "dtparam=audio=off\n")
    cfg._update_line_in_section("all", "dtoverlay=dwc2", "dtoverlay=dwc2,dr_mode=peripheral\n")
    text = "".join(cfg.lines)
    assert "[all]" in text
    assert text.index("[all]") < text.index("dtoverlay=dwc2")


def test_remove_line_only_in_named_section(tmp_path):
    cfg = _cfg(tmp_path)
    cfg._remove_line_in_section("cm4", "otg_mode=")
    text = "".join(cfg.lines)
    assert "otg_mode=1" not in text
    # unrelated sections untouched
    assert "dtoverlay=dwc2,dr_mode=host" in text
    assert "dtparam=i2c_arm=on" in text


def test_remove_is_noop_when_section_missing(tmp_path):
    cfg = _cfg(tmp_path, "dtparam=audio=off\n")
    cfg._remove_line_in_section("cm4", "otg_mode=")
    assert "".join(cfg.lines) == "dtparam=audio=off\n"
