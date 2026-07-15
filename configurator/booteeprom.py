"""Raspberry Pi bootloader EEPROM configuration.

Distinct from the HAT ID EEPROM handled by hifiberry-eeprom: this is the
bootloader EEPROM read/written with rpi-eeprom-config.
"""

import logging
import subprocess
import tempfile

# Pi 5 / CM5 send a USB PD request (5V/3A) that recent Apple hosts answer with
# PD messages the firmware cannot handle, breaking gadget enumeration entirely.
# Declaring the PSU current stops the request being sent.
# See https://github.com/raspberrypi/linux/issues/6569
PSU_WORKAROUND_VERSIONS = ("5", "CM5")

PSU_KEY = "PSU_MAX_CURRENT"


def needs_psu_workaround(version):
    """True if this Pi version must declare PSU_MAX_CURRENT for USB gadget use."""
    return version in PSU_WORKAROUND_VERSIONS


def read_eeprom_config(runner=subprocess.run):
    result = runner(["rpi-eeprom-config"], capture_output=True, text=True)
    return result.stdout


def set_psu_max_current(milliamps=3000, runner=subprocess.run):
    """Ensure PSU_MAX_CURRENT=<milliamps> in the bootloader EEPROM.

    Returns True if the EEPROM was changed, False if it was already correct.
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

    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as handle:
        handle.write(new_config)
        path = handle.name

    runner(["rpi-eeprom-config", "--apply", path], capture_output=True, text=True)
    logging.info(f"{desired} applied to bootloader EEPROM. Reboot required.")
    return True
