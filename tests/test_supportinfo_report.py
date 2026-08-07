import json
from unittest.mock import patch

from configurator import supportinfo


REPORT = {
    "System": {"Pi Model": "Raspberry Pi 5", "Sound Card": "DAC2 HD"},
    "OS": {"OS": "Debian GNU/Linux 13 (trixie)", "Kernel": "6.12.0-rpi"},
    "Packages": "hifiberry-configurator 2.15.0",
    "Services": "mpd.service loaded active running",
    "Disk": "/dev/sda1  30G  4G  25G  15% /",
    "Recent errors": "Aug 07 10:00:01 host mount[1]: password=hunter2",
}


def test_render_text_has_a_section_per_key():
    text = supportinfo.render_text(REPORT)
    for section in REPORT:
        assert f"## {section}" in text


def test_render_text_renders_dicts_as_name_value_lines():
    text = supportinfo.render_text(REPORT)
    assert "Pi Model: Raspberry Pi 5" in text


def test_render_text_redacts_secrets():
    text = supportinfo.render_text(REPORT)
    assert "hunter2" not in text
    assert supportinfo.REDACTED in text


def test_build_report_collects_every_section():
    with patch.object(supportinfo, "collect_system", return_value={"Pi Model": "Pi 5"}), \
         patch.object(supportinfo, "collect_os", return_value={"Kernel": "6.12"}), \
         patch.object(supportinfo, "collect_packages", return_value="pkg 1.0"), \
         patch.object(supportinfo, "collect_services", return_value="unit"), \
         patch.object(supportinfo, "collect_journal", return_value="err"), \
         patch.object(supportinfo, "collect_disk", return_value="df"):
        report = supportinfo.build_report()
    assert set(report) == {"System", "OS", "Packages", "Services", "Disk", "Recent errors"}


def test_redact_report_walks_nested_values():
    report = {
        "System": {"Pi Model": "Pi 5", "Note": "psk=topsecret"},
        "Recent errors": "password=hunter2",
    }
    result = supportinfo.redact_report(report)
    assert result["System"]["Pi Model"] == "Pi 5"
    assert result["System"]["Note"] == f"psk={supportinfo.REDACTED}"
    assert result["Recent errors"] == f"password={supportinfo.REDACTED}"


def test_main_json_output_is_valid_json_and_redacted(capsys):
    with patch.object(supportinfo, "build_report", return_value=dict(REPORT)):
        exit_code = supportinfo.main(["--json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    parsed = json.loads(out)
    assert parsed["System"]["Sound Card"] == "DAC2 HD"
    assert "hunter2" not in out


def test_main_default_output_is_text(capsys):
    with patch.object(supportinfo, "build_report", return_value=dict(REPORT)):
        supportinfo.main([])
    out = capsys.readouterr().out
    assert out.startswith("## System")
