"""Raspberry Pi bootloader EEPROM configuration.

Distinct from the HAT ID EEPROM handled by hifiberry-eeprom: this is the
bootloader EEPROM read/written with rpi-eeprom-config.
"""

import logging
import os
import re
import subprocess
import tempfile

# Pi 5 / CM5 send a USB PD request (5V/3A) that recent Apple hosts answer with
# PD messages the firmware cannot handle, breaking gadget enumeration entirely.
# Declaring the PSU current stops the request being sent.
# See https://github.com/raspberrypi/linux/issues/6569
PSU_WORKAROUND_VERSIONS = ("5", "CM5")

PSU_KEY = "PSU_MAX_CURRENT"

# A line that looks like a bootloader EEPROM config assignment, e.g.
# "BOOT_ORDER=0xf2461". Comment and section-header lines never match, so a
# config consisting only of those is correctly treated as not a real config.
_KEY_VALUE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class EepromConfigError(Exception):
    """Raised when the bootloader EEPROM config cannot be safely read or
    written. Callers must treat this as a hard failure: never derive a
    config from an untrustworthy read, and never report a failed apply as
    success."""


def needs_psu_workaround(version):
    """True if this Pi version must declare PSU_MAX_CURRENT for USB gadget use."""
    return version in PSU_WORKAROUND_VERSIONS


def _looks_like_eeprom_config(text):
    """True if text contains at least one real KEY=VALUE assignment line."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _KEY_VALUE_RE.match(stripped):
            return True
    return False


def read_eeprom_config(runner=subprocess.run):
    """Read the current bootloader EEPROM config.

    Raises EepromConfigError if the read failed (nonzero return code) or if
    the output does not look like a valid EEPROM config. Callers must never
    derive a config to apply from a read that raised.
    """
    result = runner(["rpi-eeprom-config"], capture_output=True, text=True)
    if result.returncode != 0:
        raise EepromConfigError(
            "rpi-eeprom-config read failed with exit code "
            f"{result.returncode}: {getattr(result, 'stderr', '') or '<no stderr>'}"
        )
    stdout = result.stdout or ""
    if not _looks_like_eeprom_config(stdout):
        raise EepromConfigError(
            "rpi-eeprom-config output does not look like a valid EEPROM "
            "config (no KEY=VALUE line found); refusing to derive a config "
            "from it to avoid overwriting the bootloader EEPROM with "
            "incomplete data."
        )
    return stdout


def set_psu_max_current(milliamps=3000, runner=subprocess.run):
    """Ensure PSU_MAX_CURRENT=<milliamps> in the bootloader EEPROM.

    Returns True if the EEPROM was changed, False if it was already correct.
    Raises EepromConfigError if the existing config could not be read
    trustworthily, or if applying the new config failed -- in neither case
    is a config ever applied that could lose existing keys (e.g. BOOT_ORDER).
    """
    current = read_eeprom_config(runner=runner)
    desired = f"{PSU_KEY}={milliamps}"
    lines = current.splitlines()

    if desired in [line.strip() for line in lines]:
        logging.info(f"{desired} already set.")
        return False

    kept = [line for line in lines if not line.strip().startswith(f"{PSU_KEY}=")]
    kept.append(desired)
    new_config = "\n".join(kept) + "\n"

    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as handle:
            handle.write(new_config)
            path = handle.name

        result = runner(["rpi-eeprom-config", "--apply", path], capture_output=True, text=True)
        if result.returncode != 0:
            raise EepromConfigError(
                "rpi-eeprom-config --apply failed with exit code "
                f"{result.returncode}: {getattr(result, 'stderr', '') or '<no stderr>'}"
            )
    finally:
        if path is not None:
            try:
                os.unlink(path)
            except OSError:
                pass

    logging.info(f"{desired} applied to bootloader EEPROM. Reboot required.")
    return True
