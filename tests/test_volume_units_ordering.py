"""volume-store must not snapshot the mixer before volume-restore has run.

Both units are pulled in at boot (volume-store also by volume-store.timer's
Requires=). Without an ordering between them, the boot-time store can save the
codec's power-on level over the stored volume, and the restore then applies
that level. On pcm512x cards the power-on level is 0 dB, i.e. full volume.
"""

import configparser
from pathlib import Path

SYSTEMD_DIR = Path(__file__).resolve().parent.parent / "systemd"


def _unit_list(unit_file, section, key):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(SYSTEMD_DIR / unit_file)
    return parser.get(section, key, fallback="").split()


def test_volume_store_runs_after_volume_restore():
    assert "volume-restore.service" in _unit_list(
        "volume-store.service", "Unit", "After"
    )


def test_volume_restore_is_not_ordered_after_volume_store():
    # The reverse ordering as well would be a cycle systemd has to break.
    assert "volume-store.service" not in _unit_list(
        "volume-restore.service", "Unit", "After"
    )
