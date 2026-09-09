"""conf.d is re-read when it changes, without restarting config-server.

ConfigParser used to load the merged config once and cache it for the life
of the process. A drop-in installed underneath a running config-server was
therefore invisible until a restart: the systemd permission lookup fell back
to its "status" default, so the Web UI showed the extension's player with
start and stop controls that did nothing, with no error and no log line.

The extension installer works around this by calling reload_config() itself,
but that only covers installs driven from the Web UI -- a plain
"apt install hifiberry-<extension>" from a shell, or an edit to a drop-in's
permission level, still went unseen.
"""
import json
import os

import pytest

from configurator import config_parser as config_parser_module
from configurator.config_parser import ConfigParser


class CountingConfigParser(ConfigParser):
    """Counts how often the config is actually read off disk."""

    def __init__(self, config_file):
        super().__init__(config_file)
        self.load_count = 0

    def load_config(self):
        self.load_count += 1
        return super().load_config()


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "configserver.json").write_text(json.dumps({"systemd": {"config-server": "all"}}))
    (tmp_path / "conf.d").mkdir()
    return tmp_path


def write_drop_in(config_dir, name, data):
    (config_dir / "conf.d" / name).write_text(json.dumps(data))


def test_drop_in_installed_after_first_read_is_picked_up(config_dir):
    parser = ConfigParser(str(config_dir / "configserver.json"))
    assert parser.get_config()["systemd"] == {"config-server": "all"}

    write_drop_in(config_dir, "analog-recognition.json",
                  {"systemd": {"analog-recognition": "all"}})

    assert parser.get_config()["systemd"]["analog-recognition"] == "all"


def test_changed_permission_level_in_a_drop_in_is_picked_up(config_dir):
    write_drop_in(config_dir, "analog-recognition.json",
                  {"systemd": {"analog-recognition": "all"}})
    parser = ConfigParser(str(config_dir / "configserver.json"))
    assert parser.get_config()["systemd"]["analog-recognition"] == "all"

    write_drop_in(config_dir, "analog-recognition.json",
                  {"systemd": {"analog-recognition": "status"}})

    assert parser.get_config()["systemd"]["analog-recognition"] == "status"


def test_removed_drop_in_stops_granting_its_permission(config_dir):
    write_drop_in(config_dir, "analog-recognition.json",
                  {"systemd": {"analog-recognition": "all"}})
    parser = ConfigParser(str(config_dir / "configserver.json"))
    assert "analog-recognition" in parser.get_config()["systemd"]

    os.remove(config_dir / "conf.d" / "analog-recognition.json")

    assert "analog-recognition" not in parser.get_config()["systemd"]


def test_edited_main_config_file_is_picked_up(config_dir):
    parser = ConfigParser(str(config_dir / "configserver.json"))
    assert parser.get_config()["systemd"] == {"config-server": "all"}

    (config_dir / "configserver.json").write_text(
        json.dumps({"systemd": {"config-server": "all", "audiocontrol": "all"}}))

    assert parser.get_config()["systemd"]["audiocontrol"] == "all"


def test_unchanged_config_is_not_re_read_on_every_call(config_dir):
    write_drop_in(config_dir, "analog-recognition.json",
                  {"systemd": {"analog-recognition": "all"}})
    parser = CountingConfigParser(str(config_dir / "configserver.json"))

    for _ in range(5):
        parser.get_config()

    assert parser.load_count == 1


def test_conf_d_appearing_later_is_picked_up(tmp_path):
    """The drop-in directory itself need not exist at first read: an image
    build can leave /etc/configserver/conf.d absent until the first extension
    package creates it."""
    (tmp_path / "configserver.json").write_text(json.dumps({"systemd": {}}))
    parser = ConfigParser(str(tmp_path / "configserver.json"))
    assert parser.get_config()["systemd"] == {}

    (tmp_path / "conf.d").mkdir()
    (tmp_path / "conf.d" / "analog-recognition.json").write_text(
        json.dumps({"systemd": {"analog-recognition": "all"}}))

    assert parser.get_config()["systemd"]["analog-recognition"] == "all"


def test_unreadable_config_is_not_re_read_on_every_call(tmp_path):
    """A missing or invalid config file must cache its empty result like any
    other. get_config() runs on every permission lookup, and each failed read
    logs at error level -- re-reading per call would fill the journal."""
    parser = CountingConfigParser(str(tmp_path / "configserver.json"))

    for _ in range(5):
        assert parser.get_config() == {}

    assert parser.load_count == 1


def test_config_file_appearing_later_is_picked_up(tmp_path):
    parser = ConfigParser(str(tmp_path / "configserver.json"))
    assert parser.get_config() == {}

    (tmp_path / "configserver.json").write_text(json.dumps({"systemd": {"config-server": "all"}}))

    assert parser.get_config()["systemd"]["config-server"] == "all"


def test_repaired_invalid_config_file_is_picked_up(tmp_path):
    (tmp_path / "configserver.json").write_text("{ not json")
    parser = ConfigParser(str(tmp_path / "configserver.json"))
    assert parser.get_config() == {}

    (tmp_path / "configserver.json").write_text(json.dumps({"systemd": {"config-server": "all"}}))

    assert parser.get_config()["systemd"]["config-server"] == "all"


def test_config_that_cannot_be_opened_is_not_re_read_on_every_call(tmp_path):
    """The catch-all read failure caches like the others -- a config file that
    cannot be opened at all (here a directory in its place; on a device, a
    permission or I/O error) would otherwise log on every permission lookup."""
    (tmp_path / "configserver.json").mkdir()
    parser = CountingConfigParser(str(tmp_path / "configserver.json"))

    for _ in range(5):
        assert parser.get_config() == {}

    assert parser.load_count == 1


def test_invalid_config_file_is_not_re_read_on_every_call(tmp_path):
    (tmp_path / "configserver.json").write_text("{ not json")
    parser = CountingConfigParser(str(tmp_path / "configserver.json"))

    for _ in range(5):
        assert parser.get_config() == {}

    assert parser.load_count == 1


@pytest.fixture
def fake_clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(config_parser_module.time, "monotonic", lambda: now[0])
    return now


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits this test relies on")
def test_transient_read_failure_is_retried(tmp_path, fake_clock):
    """A read that fails for a reason outside the file's contents -- an I/O
    error off a worn card, fd exhaustion, an EACCES window while permissions
    are being fixed -- can clear without the file's mtime or size changing. The
    fingerprint alone would then never re-read, leaving every permission lookup
    on its "status" fallback for the life of the process: the very symptom
    conf.d change detection exists to prevent."""
    cfg = tmp_path / "configserver.json"
    cfg.write_text(json.dumps({"systemd": {"config-server": "all"}}))
    os.chmod(cfg, 0o000)

    parser = ConfigParser(str(cfg))
    assert parser.get_config() == {}

    before = os.stat(cfg)
    os.chmod(cfg, 0o644)
    after = os.stat(cfg)
    assert (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size)

    fake_clock[0] += 300

    assert parser.get_config()["systemd"]["config-server"] == "all"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits this test relies on")
def test_transient_read_failure_is_not_retried_on_every_call(tmp_path, fake_clock):
    cfg = tmp_path / "configserver.json"
    cfg.write_text(json.dumps({"systemd": {"config-server": "all"}}))
    os.chmod(cfg, 0o000)

    parser = CountingConfigParser(str(cfg))
    for _ in range(5):
        assert parser.get_config() == {}

    assert parser.load_count == 1
