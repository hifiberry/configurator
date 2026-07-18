#!/usr/bin/env python3

import os
import sys
import shutil
import hashlib
import logging
import argparse
from typing import Optional, List, Any
from .soundcard import Soundcard

# Constants
HIFIBERRY_DETECTION_DISABLED = "# HiFiBerry sound detection disabled"
"""Comment string used to disable HiFiBerry auto-detection."""


class ConfigTxt:
    """Manage Raspberry Pi /boot/firmware/config.txt configuration.
    
    Provides methods to enable/disable various hardware interfaces,
    manage sound card configurations, and apply device tree overlays.
    """

    def __init__(self, file_path: str = "/boot/firmware/config.txt") -> None:
        """Initialize ConfigTxt with path to config.txt.
        
        Args:
            file_path: Path to config.txt file (default: /boot/firmware/config.txt)
            
        Raises:
            FileNotFoundError: If the config.txt file does not exist
        """
        self.file_path = file_path
        self.lines = []
        self.changes_made = False
        self.original_checksum = None
        self._read_file()

    def _read_file(self) -> None:
        """Reads the content of the config file into the buffer and computes its checksum."""
        if not os.path.exists(self.file_path):
            logging.error(f"Config file not found: {self.file_path}")
            raise FileNotFoundError(f"Config file not found: {self.file_path}")

        with open(self.file_path, "r") as file:
            self.lines = file.readlines()

        self.original_checksum = self._compute_checksum(self.lines)

    def is_detection_disabled(self) -> bool:
        """Check if HiFiBerry detection is disabled in config.txt.
        
        Returns:
            bool: True if HIFIBERRY_DETECTION_DISABLED comment is found, False otherwise
        """
        for line in self.lines:
            if line.strip() == HIFIBERRY_DETECTION_DISABLED:
                return True
        return False

    def enable_detection(self) -> None:
        """Enable HiFiBerry detection by removing the disabled comment."""
        original_length = len(self.lines)
        self.lines = [line for line in self.lines if line.strip() != HIFIBERRY_DETECTION_DISABLED]
        if len(self.lines) < original_length:
            logging.info("HiFiBerry detection enabled (removed disabled comment).")
        else:
            logging.info("HiFiBerry detection already enabled.")

    def disable_detection(self) -> None:
        """Disable HiFiBerry detection by adding the disabled comment at the end."""
        # Check if already disabled
        if self.is_detection_disabled():
            logging.info("HiFiBerry detection already disabled.")
            return
        
        # Add the disabled comment at the end of the file
        self.lines.append(f"{HIFIBERRY_DETECTION_DISABLED}\n")
        logging.info("HiFiBerry detection disabled.")

    def _compute_checksum(self, lines: List[str]) -> str:
        """Compute SHA256 checksum of file lines.
        
        Args:
            lines: List of file lines
            
        Returns:
            Hexadecimal SHA256 hash of the content
        """
        content = "".join(lines).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def save(self) -> None:
        """Write buffer to config file and create backup if changes were made."""
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

    def _update_line(self, prefix: str, new_line: str) -> None:
        """Update or add a line with the specified prefix.
        
        Searches for a line starting with `prefix` and replaces it.
        If not found, appends `new_line` to the end of the file.
        
        Args:
            prefix: String prefix to search for
            new_line: Complete line to insert/replace (should include newline)
        """
        for i, line in enumerate(self.lines):
            if line.strip().startswith(prefix):
                self.lines[i] = new_line
                return
        self.lines.append(new_line)

    def disable_onboard_sound(self) -> None:
        """Disable the onboard sound."""
        self._update_line("dtparam=audio=", "dtparam=audio=off\n")
        logging.info("Onboard sound disabled.")

    def enable_onboard_sound(self) -> None:
        """Enable the onboard sound."""
        self._update_line("dtparam=audio=", "dtparam=audio=on\n")
        logging.info("Onboard sound enabled.")

    def _update_hdmi_sound(self, mode: str) -> None:
        """Update HDMI sound setting.
        
        Args:
            mode: Either 'audio' to enable or 'noaudio' to disable
        """
        for i, line in enumerate(self.lines):
            if line.strip().startswith("dtoverlay=vc4-kms-v3d"):
                if mode == "noaudio" and ",noaudio" not in line:
                    self.lines[i] = line.strip() + ",noaudio\n"
                    return
                elif mode == "audio" and ",noaudio" in line:
                    self.lines[i] = line.replace(",noaudio", "").strip() + "\n"
                    return

    def disable_hdmi_sound(self) -> None:
        """Disable HDMI sound."""
        self._update_hdmi_sound("noaudio")
        logging.info("HDMI sound disabled.")

    def enable_hdmi_sound(self) -> None:
        """Enable HDMI sound."""
        self._update_hdmi_sound("audio")
        logging.info("HDMI sound enabled.")

    def disable_eeprom(self) -> None:
        """Disable EEPROM read."""
        self._update_line("force_eeprom_read=", "force_eeprom_read=0\n")
        logging.info("EEPROM read disabled.")

    def enable_eeprom(self) -> None:
        """Enable EEPROM read."""
        self._update_line("force_eeprom_read=", "force_eeprom_read=1\n")
        logging.info("EEPROM read enabled.")

    def enable_overlay(self, overlay: str, card_name: Optional[str] = None,
                       disable_eeprom: bool = False) -> None:
        """Enable a device tree overlay.
        
        Optionally adds a HiFiBerry card name comment and disables EEPROM.
        
        Args:
            overlay: Name of the overlay to enable (e.g., 'hifiberry-dac')
            card_name: Optional human-readable name for the card
            disable_eeprom: Whether to disable EEPROM read
        """
        if card_name:
            self.lines.append(f"# HiFiBerry card: {card_name}\n")
        if disable_eeprom:
            self.lines.append("force_eeprom_read=0\n")
        self.lines.append(f"dtoverlay={overlay}\n")
        logging.info(f"Overlay '{overlay}' enabled.")

    def remove_hifiberry_overlays(self) -> None:
        """Remove all HiFiBerry overlays, detection comment, and EEPROM settings."""
        original_length = len(self.lines)
        # Remove HiFiBerry overlays, detection disabled comment, card comments, etc.
        self.lines = [line for line in self.lines
                      if not line.strip().startswith("dtoverlay=hifiberry")
                      and line.strip() != HIFIBERRY_DETECTION_DISABLED
                      and not line.strip().startswith("# HiFiBerry card:")
                      and not line.strip().startswith("force_eeprom_read=")]
        if len(self.lines) < original_length:
            logging.info("All HiFiBerry overlays and detection comment removed.")

    def _update_interface(self, interface: str, enable: bool) -> None:
        """Update interface enabled/disabled status.
        
        Args:
            interface: Interface name (e.g., 'i2c_arm', 'spi')
            enable: True to enable, False to disable
        """
        state = "on" if enable else "off"
        self._update_line(f"dtparam={interface}=", f"dtparam={interface}={state}\n")
        logging.info(f"{interface.upper()} interface set to {state}.")

    def enable_i2c(self) -> None:
        """Enable I2C interface."""
        self._update_interface("i2c_arm", True)

    def disable_i2c(self) -> None:
        """Disable I2C interface."""
        self._update_interface("i2c_arm", False)

    def enable_spi(self) -> None:
        """Enable SPI interface."""
        self._update_interface("spi", True)

    def disable_spi(self) -> None:
        """Disable SPI interface."""
        self._update_interface("spi", False)

    def default_config(self) -> None:
        """Apply default configuration settings."""
        self.remove_hifiberry_overlays()
        self.disable_onboard_sound()
        self.disable_hdmi_sound()
        self.enable_eeprom()
        self.enable_spi()
        self.enable_i2c()
        self.disable_hat_i2c()
        logging.info("Default configuration applied. I2C enabled.")

    def enable_updi(self) -> None:
        """Enable UPDI settings: UART, uart0, and disable Bluetooth."""
        self._update_line("enable_uart=", "enable_uart=1\n")
        self._update_line("dtoverlay=uart0", "dtoverlay=uart0\n")
        self._update_line("dtoverlay=disable-bt", "dtoverlay=disable-bt\n")
        logging.info("UPDI settings applied. Reboot may be required.")

    def enable_hat_i2c(self) -> None:
        """Enable HAT I2C overlay with GPIO pins."""
        overlay_line = "dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1\n"
        # Prevent duplicates if the line already exists
        if not any(line.strip() == overlay_line.strip() for line in self.lines):
            self.lines.append(overlay_line)
            logging.info("HAT I2C overlay enabled.")

    def disable_hat_i2c(self) -> None:
        """Disable HAT I2C overlay."""
        original_length = len(self.lines)
        overlay_line = "dtoverlay=i2c-gpio,i2c_gpio_sda=0,i2c_gpio_scl=1"
        self.lines = [line for line in self.lines if line.strip() != overlay_line]
        if len(self.lines) < original_length:
            logging.info("HAT I2C overlay disabled.")

    def autodetect_overlay(self) -> None:
        """Detect current sound card and add appropriate overlay.
        
        Raises:
            Exception: If auto-detection fails
        """
        if self.is_detection_disabled():
            logging.info("HiFiBerry detection is disabled. Skipping auto-detect overlay.")
            return
        
        # Remove existing HiFiBerry overlays before adding the new one
        self.remove_hifiberry_overlays()
        
        try:
            soundcard = Soundcard()
            name: str | None = getattr(soundcard, 'name', None)
            if name:
                # Get the sound card definition from the soundcard module
                from .soundcard import SOUND_CARD_DEFINITIONS
                card_def: dict[str, Any] | None = SOUND_CARD_DEFINITIONS.get(name)
                if card_def is not None:
                    overlay_val: Any = card_def.get("dtoverlay")
                    if overlay_val and isinstance(overlay_val, str):
                        self.enable_overlay(overlay_val)
                        msg = f"Auto-detected '{name}', enabled '{overlay_val}'."
                        logging.info(msg)
                    else:
                        msg = f"Auto-detected '{name}', no overlay defined."
                        logging.warning(msg)
                else:
                    msg = f"Auto-detected '{name}', no overlay defined."
                    logging.warning(msg)
            else:
                # Fallback to hifiberry-dac if no sound card is detected
                fallback_overlay = "hifiberry-dac"
                self.enable_overlay(fallback_overlay)
                logging.info(f"No sound card detected, using fallback '{fallback_overlay}'.")
        except Exception as e:
            logging.error(f"Failed to auto-detect overlay: {e}")
            raise


def main() -> int:
    """Main entry point for command-line configuration management."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Manage /boot/firmware/config.txt settings."
    )
    parser.add_argument(
        "--overlay", type=str, help="Add a dtoverlay with the given parameter."
    )
    parser.add_argument(
        "--autodetect-overlay", action="store_true",
        help="Auto-detect sound card and add the appropriate overlay."
    )
    parser.add_argument(
        "--remove-hifiberry", action="store_true",
        help="Remove all HiFiBerry overlays."
    )
    parser.add_argument(
        "--disable-onboard-sound", action="store_true",
        help="Disable onboard sound."
    )
    parser.add_argument(
        "--enable-onboard-sound", action="store_true",
        help="Enable onboard sound."
    )
    parser.add_argument(
        "--disable-hdmi-sound", action="store_true",
        help="Disable HDMI sound."
    )
    parser.add_argument(
        "--enable-hdmi-sound", action="store_true",
        help="Enable HDMI sound."
    )
    parser.add_argument(
        "--disable-eeprom", action="store_true",
        help="Disable EEPROM read."
    )
    parser.add_argument(
        "--enable-eeprom", action="store_true",
        help="Enable EEPROM read."
    )
    parser.add_argument(
        "--disable-i2c", action="store_true",
        help="Disable I2C interface."
    )
    parser.add_argument(
        "--enable-i2c", action="store_true",
        help="Enable I2C interface."
    )
    parser.add_argument(
        "--disable-spi", action="store_true",
        help="Disable SPI interface."
    )
    parser.add_argument(
        "--enable-spi", action="store_true",
        help="Enable SPI interface."
    )
    parser.add_argument(
        "--default-config", action="store_true",
        help="Apply the default configuration."
    )
    parser.add_argument(
        "--report-change", action="store_true",
        help="Exit with return code 1 if changes were made."
    )
    parser.add_argument(
        "--enable-updi", action="store_true",
        help="Enable UPDI settings: enable UART, dtoverlay for uart0, and disable BT."
    )
    parser.add_argument(
        "--enable-hat_i2c", action="store_true",
        help="Enable HAT I2C overlay (i2c-gpio with SDA=0, SCL=1)."
    )
    parser.add_argument(
        "--disable-hat_i2c", action="store_true",
        help="Disable HAT I2C overlay."
    )
    parser.add_argument(
        "--enable-detection", action="store_true",
        help="Enable HiFiBerry sound card detection."
    )
    parser.add_argument(
        "--disable-detection", action="store_true",
        help="Disable HiFiBerry sound card detection."
    )
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
            return 1 if config.changes_made else 0

        logging.info("Configuration update completed successfully.")
        return 0
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        if args.report_change:
            return 1
        return 1


if __name__ == "__main__":
    sys.exit(main())

