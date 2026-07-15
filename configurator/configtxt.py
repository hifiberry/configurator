#!/usr/bin/env python3

import os
import shutil
import hashlib
import logging
import argparse
from typing import Optional
from .soundcard import Soundcard
from .pimodel import PiModel

# Constants
HIFIBERRY_DETECTION_DISABLED = "# HiFiBerry sound detection disabled"
DWC2_PREFIX = "dtoverlay=dwc2"
DWC2_PERIPHERAL = "dtoverlay=dwc2,dr_mode=peripheral\n"
DWC2_HOST = "dtoverlay=dwc2,dr_mode=host\n"

# Pi model version -> the config.txt model section it boots from, for models
# that have one. Models not listed here have no dedicated model section.
DWC2_MODEL_SECTION = {
    "CM5": "cm5",
    "5": "pi5",
    "CM4": "cm4",
    "4": "pi4",
}


class UnsupportedModelError(Exception):
    """Raised when the detected Pi model cannot act as a USB peripheral."""


class ConfigTxt:
    def __init__(self, file_path = "/boot/firmware/config.txt"):
        self.file_path = file_path
        self.lines = []
        self.changes_made = False
        self.original_checksum = None
        self._read_file()

    def _read_file(self):
        """Reads the content of the config file into the buffer and computes its checksum."""
        if not os.path.exists(self.file_path):
            logging.error(f"Config file not found: {self.file_path}")
            raise FileNotFoundError(f"Config file not found: {self.file_path}")

        with open(self.file_path, "r") as file:
            self.lines = file.readlines()

        self.original_checksum = self._compute_checksum(self.lines)

    def is_detection_disabled(self):
        """Check if HiFiBerry detection is disabled in config.txt
        
        Returns:
            bool: True if HIFIBERRY_DETECTION_DISABLED comment is found, False otherwise
        """
        for line in self.lines:
            if line.strip() == HIFIBERRY_DETECTION_DISABLED:
                return True
        return False

    def enable_detection(self):
        """Enable HiFiBerry detection by removing the disabled comment"""
        original_length = len(self.lines)
        self.lines = [line for line in self.lines if line.strip() != HIFIBERRY_DETECTION_DISABLED]
        if len(self.lines) < original_length:
            logging.info("HiFiBerry detection enabled (removed disabled comment).")
        else:
            logging.info("HiFiBerry detection already enabled.")

    def disable_detection(self):
        """Disable HiFiBerry detection by adding the disabled comment at the end"""
        # Check if already disabled
        if self.is_detection_disabled():
            logging.info("HiFiBerry detection already disabled.")
            return
        
        # Add the disabled comment at the end of the file
        self.lines.append(f"{HIFIBERRY_DETECTION_DISABLED}\n")
        logging.info("HiFiBerry detection disabled.")

    def _compute_checksum(self, lines):
        """Computes the checksum of the given lines."""
        content = "".join(lines).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def save(self):
        """Writes the buffer back to the config file if changes were made and creates a backup if the file has changed."""
        new_checksum = self._compute_checksum(self.lines)
        if new_checksum != self.original_checksum:
            backup_path = self.file_path + ".backup"
            shutil.copy(self.file_path, backup_path)
            logging.info(f"Backup created at: {backup_path}")

            with open(self.file_path, "w") as file:
                file.writelines(self.lines)

            logging.info("Changes saved to the config file.")
            self.changes_made = True
        else:
            self.changes_made = False

    def _update_line(self, prefix, new_line):
        """Updates or adds a line with the specified prefix."""
        updated = False
        for i, line in enumerate(self.lines):
            if line.strip().startswith(prefix):
                self.lines[i] = new_line
                updated = True
                break
        if not updated:
            self.lines.append(new_line)

    def _section_bounds(self, section):
        """Return (start, end) line indices of a [section] body, or None if absent.

        start is the first line after the [section] header; end is the index of
        the next section header (or len(lines) at EOF).
        """
        header = f"[{section}]"
        start = None
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if start is None:
                if stripped == header:
                    start = i + 1
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                return (start, i)
        if start is None:
            return None
        return (start, len(self.lines))

    def _ensure_section(self, section):
        """Return (start, end) for a section, creating it at EOF if needed."""
        bounds = self._section_bounds(section)
        if bounds is not None:
            return bounds
        if self.lines and not self.lines[-1].endswith("\n"):
            self.lines[-1] += "\n"
        self.lines.append(f"\n[{section}]\n")
        return (len(self.lines), len(self.lines))

    def _update_line_in_section(self, section, prefix, new_line):
        """Update or insert a line with the given prefix inside [section]."""
        start, end = self._ensure_section(section)
        for i in range(start, end):
            if self.lines[i].strip().startswith(prefix):
                self.lines[i] = new_line
                logging.info(f"Updated '{prefix}' in [{section}].")
                return
        self.lines.insert(end, new_line)
        logging.info(f"Added '{new_line.strip()}' to [{section}].")

    def _remove_line_in_section(self, section, prefix):
        """Remove any line with the given prefix inside [section]."""
        bounds = self._section_bounds(section)
        if bounds is None:
            return
        start, end = bounds
        kept = [
            line for i, line in enumerate(self.lines)
            if not (start <= i < end and line.strip().startswith(prefix))
        ]
        if len(kept) != len(self.lines):
            self.lines = kept
            logging.info(f"Removed '{prefix}' from [{section}].")

    def disable_onboard_sound(self):
        self._update_line("dtparam=audio=", "dtparam=audio=off\n")
        logging.info("Onboard sound disabled.")

    def enable_onboard_sound(self):
        self._update_line("dtparam=audio=", "dtparam=audio=on\n")
        logging.info("Onboard sound enabled.")

    def _update_hdmi_sound(self, mode):
        updated = False
        for i, line in enumerate(self.lines):
            if line.strip().startswith("dtoverlay=vc4-kms-v3d"):
                if mode == "noaudio" and ",noaudio" not in line:
                    self.lines[i] = line.strip() + ",noaudio\n"
                    updated = True
                elif mode == "audio" and ",noaudio" in line:
                    self.lines[i] = line.replace(",noaudio", "").strip() + "\n"
                    updated = True

    def disable_hdmi_sound(self):
        self._update_hdmi_sound("noaudio")
        logging.info("HDMI sound disabled.")

    def enable_hdmi_sound(self):
        self._update_hdmi_sound("audio")
        logging.info("HDMI sound enabled.")

    def disable_eeprom(self):
        self._update_line("force_eeprom_read=", "force_eeprom_read=0\n")
        logging.info("EEPROM read disabled.")

    def enable_eeprom(self):
        self._update_line("force_eeprom_read=", "force_eeprom_read=1\n")
        logging.info("EEPROM read enabled.")

    def enable_overlay(self, overlay, card_name=None, disable_eeprom=False):
        """Enable a device tree overlay, optionally with a card name comment and EEPROM disable"""
        if card_name:
            self.lines.append(f"# HiFiBerry card: {card_name}\n")
        if disable_eeprom:
            self.lines.append("force_eeprom_read=0\n")
        self.lines.append(f"dtoverlay={overlay}\n")
        logging.info(f"Overlay '{overlay}' enabled.")

    def remove_hifiberry_overlays(self):
        original_length = len(self.lines)
        # Remove HiFiBerry overlays, detection disabled comment, card comments, and force_eeprom_read
        self.lines = [line for line in self.lines 
                      if not line.strip().startswith("dtoverlay=hifiberry") 
                      and line.strip() != HIFIBERRY_DETECTION_DISABLED
                      and not line.strip().startswith("# HiFiBerry card:")
                      and not line.strip().startswith("force_eeprom_read=")]
        if len(self.lines) < original_length:
            logging.info("All HiFiBerry overlays and detection comment removed.")

    def _update_interface(self, interface, enable):
        state = "on" if enable else "off"
        self._update_line(f"dtparam={interface}=", f"dtparam={interface}={state}\n")
        logging.info(f"{interface.upper()} interface set to {state}.")

    def enable_i2c(self):
        self._update_interface("i2c_arm", True)

    def disable_i2c(self):
        self._update_interface("i2c_arm", False)

    def enable_spi(self):
        self._update_interface("spi", True)

    def disable_spi(self):
        self._update_interface("spi", False)

    def default_config(self):
        self.remove_hifiberry_overlays()
        self.disable_onboard_sound()
        self.disable_hdmi_sound()
        self.enable_eeprom()
        self.enable_spi()
        self.enable_i2c()
        self.disable_hat_i2c()
        logging.info("Default configuration applied. I2C enabled.")

    def enable_updi(self):
        """
        Enables UPDI by ensuring the following entries exist in the config file:
        - enable_uart=1
        - dtoverlay=uart0
        - dtoverlay=disable-bt
        """
        self._update_line("enable_uart=", "enable_uart=1\n")
        self._update_line("dtoverlay=uart0", "dtoverlay=uart0\n")
        self._update_line("dtoverlay=disable-bt", "dtoverlay=disable-bt\n")
        logging.info("UPDI settings applied. Reboot may be required.")

    def _dwc2_owner_section(self, version):
        """Return the version's own config.txt section name if it already
        contains a dtoverlay=dwc2 line, else None.

        A real config.txt carries every model's section at once (that's the
        whole point of conditional sections -- one image boots many boards).
        A model section that exists but has no dwc2 line in it (e.g. [cm4],
        which only ever carries otg_mode=1) -- or a model with no section of
        its own at all -- must NOT be treated as owning the dwc2 line: only
        the section the *current* model actually reads, and that already has
        a dwc2 line in stock config.txt, counts. Everything else falls back
        to [all], per Raspberry Pi's own guidance for models that don't ship
        their own dwc2 line.
        """
        model_section = DWC2_MODEL_SECTION.get(version)
        if model_section is None:
            return None
        bounds = self._section_bounds(model_section)
        if bounds is None:
            return None
        start, end = bounds
        for i in range(start, end):
            if self.lines[i].strip().startswith(DWC2_PREFIX):
                return model_section
        return None

    def enable_usb_gadget(self, pi_model=None):
        """Switch the dwc2 controller to peripheral mode so the Pi can be a gadget."""
        pi_model = pi_model or PiModel()
        if not pi_model.supports_usb_gadget():
            raise UnsupportedModelError(
                f"{pi_model.get_model_name()} has no USB device-mode port"
            )
        # otg_mode=1 forces the XHCI host controller and defeats dwc2 device mode.
        self._remove_line_in_section("cm4", "otg_mode=")
        self._remove_line_in_section("all", "otg_mode=")
        section = self._dwc2_owner_section(pi_model.get_version()) or "all"
        self._update_line_in_section(section, DWC2_PREFIX, DWC2_PERIPHERAL)
        logging.info("USB gadget mode enabled. Reboot required.")

    def disable_usb_gadget(self, pi_model=None):
        """Restore dwc2 host mode, undoing exactly what enable_usb_gadget did."""
        pi_model = pi_model or PiModel()
        owner = self._dwc2_owner_section(pi_model.get_version())
        if owner:
            # Stock model section already had a dwc2 line (e.g. CM5) -- flip
            # it back to host mode in place.
            self._update_line_in_section(owner, DWC2_PREFIX, DWC2_HOST)
        else:
            # enable_usb_gadget added this line to [all] itself; remove it
            # rather than leaving behind a line that was never there before.
            self._remove_line_in_section("all", DWC2_PREFIX)
        if pi_model.get_version() == "CM4":
            # Restore the stock XHCI host controller otg_mode=1 that enable
            # stripped, otherwise the board is silently downgraded to dwc2's
            # slower built-in host mode.
            self._update_line_in_section("cm4", "otg_mode=", "otg_mode=1\n")
        logging.info("USB gadget mode disabled. Reboot required.")

    def enable_hat_i2c(self):
        overlay_line = "dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1\n"
        # Prevent duplicates if the line already exists
        if not any(line.strip() == overlay_line.strip() for line in self.lines):
            self.lines.append(overlay_line)
            logging.info("HAT I2C overlay enabled.")

    def disable_hat_i2c(self):
        original_length = len(self.lines)
        self.lines = [line for line in self.lines if line.strip() != "dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1"]
        if len(self.lines) < original_length:
            logging.info("HAT I2C overlay disabled.")

    def autodetect_overlay(self):
        """
        Detect the current sound card and automatically add the appropriate overlay.
        """
        if self.is_detection_disabled():
            logging.info("HiFiBerry detection is disabled. Skipping auto-detect overlay.")
            return
        
        # Remove existing HiFiBerry overlays before adding the new one
        self.remove_hifiberry_overlays()
        
        try:
            soundcard = Soundcard()
            if soundcard.name:
                # Get the sound card definition from the soundcard module
                from .soundcard import SOUND_CARD_DEFINITIONS
                card_def = SOUND_CARD_DEFINITIONS.get(soundcard.name)
                if card_def and card_def.get("dtoverlay"):
                    overlay = card_def["dtoverlay"]
                    self.enable_overlay(overlay)
                    logging.info(f"Auto-detected sound card '{soundcard.name}' and enabled overlay '{overlay}'.")
                else:
                    logging.warning(f"Auto-detected sound card '{soundcard.name}' but no overlay found in definitions.")
            else:
                # Fallback to hifiberry-dac if no sound card is detected
                fallback_overlay = "hifiberry-dac"
                self.enable_overlay(fallback_overlay)
                logging.info(f"No sound card detected, using fallback overlay '{fallback_overlay}'.")
        except Exception as e:
            logging.error(f"Failed to auto-detect overlay: {e}")
            raise


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Manage /boot/firmware/config.txt settings.")
    parser.add_argument("--overlay", type=str, help="Add a dtoverlay with the given parameter.")
    parser.add_argument("--autodetect-overlay", action="store_true", help="Auto-detect sound card and add the appropriate overlay.")
    parser.add_argument("--remove-hifiberry", action="store_true", help="Remove all HiFiBerry overlays.")
    parser.add_argument("--disable-onboard-sound", action="store_true", help="Disable onboard sound.")
    parser.add_argument("--enable-onboard-sound", action="store_true", help="Enable onboard sound.")
    parser.add_argument("--disable-hdmi-sound", action="store_true", help="Disable HDMI sound.")
    parser.add_argument("--enable-hdmi-sound", action="store_true", help="Enable HDMI sound.")
    parser.add_argument("--disable-eeprom", action="store_true", help="Disable EEPROM read.")
    parser.add_argument("--enable-eeprom", action="store_true", help="Enable EEPROM read.")
    parser.add_argument("--disable-i2c", action="store_true", help="Disable I2C interface.")
    parser.add_argument("--enable-i2c", action="store_true", help="Enable I2C interface.")
    parser.add_argument("--disable-spi", action="store_true", help="Disable SPI interface.")
    parser.add_argument("--enable-spi", action="store_true", help="Enable SPI interface.")
    parser.add_argument("--default-config", action="store_true", help="Apply the default configuration.")
    parser.add_argument("--report-change", action="store_true", help="Exit with return code 1 if changes were made.")
    parser.add_argument("--enable-updi", action="store_true", help="Enable UPDI settings: enable UART, dtoverlay for uart0, and disable Bluetooth.")
    parser.add_argument("--enable-usb-gadget", action="store_true", help="Enable USB device (gadget) mode on the OTG port.")
    parser.add_argument("--disable-usb-gadget", action="store_true", help="Restore USB host mode on the OTG port.")
    parser.add_argument("--enable-hat_i2c", action="store_true", help="Enable HAT I2C overlay (dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1).")
    parser.add_argument("--disable-hat_i2c", action="store_true", help="Disable HAT I2C overlay (dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1).")
    parser.add_argument("--enable-detection", action="store_true", help="Enable HiFiBerry sound card detection.")
    parser.add_argument("--disable-detection", action="store_true", help="Disable HiFiBerry sound card detection.")
    args = parser.parse_args()

    config = ConfigTxt()

    try:
        if args.default_config:
            config.default_config()

        if args.remove_hifiberry:
            config.remove_hifiberry_overlays()

        if args.overlay:
            config.enable_overlay(args.overlay)

        if args.autodetect_overlay:
            config.autodetect_overlay()

        if args.disable_onboard_sound:
            config.disable_onboard_sound()

        if args.enable_onboard_sound:
            config.enable_onboard_sound()

        if args.disable_hdmi_sound:
            config.disable_hdmi_sound()

        if args.enable_hdmi_sound:
            config.enable_hdmi_sound()

        if args.disable_eeprom:
            config.disable_eeprom()

        if args.enable_eeprom:
            config.enable_eeprom()

        if args.disable_i2c:
            config.disable_i2c()

        if args.enable_i2c:
            config.enable_i2c()

        if args.disable_spi:
            config.disable_spi()

        if args.enable_spi:
            config.enable_spi()

        if args.enable_updi:
            config.enable_updi()

        if args.enable_usb_gadget:
            config.enable_usb_gadget()

        if args.disable_usb_gadget:
            config.disable_usb_gadget()

        if args.enable_hat_i2c:
            config.enable_hat_i2c()

        if args.disable_hat_i2c:
            config.disable_hat_i2c()

        if args.enable_detection:
            config.enable_detection()

        if args.disable_detection:
            config.disable_detection()

        config.save()

        if args.report_change:
            exit(1 if config.changes_made else 0)

        logging.info("Configuration update completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        if args.report_change:
            exit(1)


if __name__ == "__main__":
    main()

