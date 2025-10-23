#!/usr/bin/env python3

import os
import subprocess
import logging
import argparse
import time
from datetime import datetime
from configurator.configtxt import ConfigTxt
from configurator.hattools import get_hat_info  # Import the get_hat_info module
from configurator.dsptoolkit import detect_dsp
from configurator.soundcard import Soundcard

# Constants
HIFIBERRY_CARD_COMMENT_PREFIX = "# HiFiBerry card:"

# Additional validation tests for sound cards
# These functions provide extra verification beyond basic detection
SOUND_CARD_VALIDATION_TESTS = {
    "dacplusdsp": lambda: _validate_dsp_card(),
    # Add more validation tests here as needed
}

def _validate_dsp_card():
    """
    Validate that a DSP card actually has a functioning DSP
    
    Returns:
        bool: True if DSP is detected, False otherwise
    """
    try:
        dsp_info = detect_dsp(timeout=2.0)
        if dsp_info and dsp_info.get("status") == "detected":
            detected_dsp = dsp_info.get("detected_dsp", "")
            logging.info(f"DSP validation: Found {detected_dsp}")
            return "ADAU14" in detected_dsp
        else:
            logging.warning("DSP validation: No DSP detected")
            return False
    except Exception as e:
        logging.warning(f"DSP validation failed: {e}")
        return False

class SoundcardDetector:
    def __init__(self, config_file="/boot/firmware/config.txt", reboot_file="/tmp/reboot", hifiberry_log_file=None, hat_attempts=1):
        self.config = ConfigTxt(config_file)
        self.reboot_file = reboot_file
        self.detected_card = None  # Card name (e.g., "DAC+ DSP")
        self.detected_overlay = None  # Overlay name (e.g., "dacplusdsp")
        self.eeprom = 1
        self.hifiberry_log_file = hifiberry_log_file
        self.hifiberry_logger = None
        self.hat_attempts = hat_attempts
        
        # Setup HiFiBerry logging if requested
        if self.hifiberry_log_file:
            self._setup_hifiberry_logger()

    def _setup_hifiberry_logger(self):
        """Setup a separate logger for HiFiBerry-specific events"""
        self.hifiberry_logger = logging.getLogger('hifiberry_events')
        self.hifiberry_logger.setLevel(logging.INFO)
        
        # Create file handler
        handler = logging.FileHandler(self.hifiberry_log_file)
        handler.setLevel(logging.INFO)
        
        # Create formatter with timestamp
        formatter = logging.Formatter('%(asctime)s - %(message)s', 
                                    datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        
        # Add handler to logger (avoid duplicates)
        if not self.hifiberry_logger.handlers:
            self.hifiberry_logger.addHandler(handler)
            
        # Prevent propagation to root logger to avoid duplicate messages
        self.hifiberry_logger.propagate = False

    def _log_hifiberry_event(self, message):
        """Log a HiFiBerry-specific event to both standard and HiFiBerry logs"""
        logging.info(message)  # Standard logging
        if self.hifiberry_logger:
            self.hifiberry_logger.info(message)  # HiFiBerry-specific logging

    def _remove_hifiberry_comments(self):
        """Remove existing HiFiBerry card comments from config.txt"""
        original_length = len(self.config.lines)
        self.config.lines = [line for line in self.config.lines if not line.strip().startswith(HIFIBERRY_CARD_COMMENT_PREFIX)]
        if len(self.config.lines) < original_length:
            logging.debug("Removed existing HiFiBerry card comments.")

    def detect_from_config_txt_comment(self):
        """
        Parse config.txt and return the card name from HiFiBerry comments
        
        Looks for lines like "# HiFiBerry card: DAC+ DSP" and extracts the card name
        
        Returns:
            str: Card name if found in comment, None if no comment found
        """
        logging.info("Detecting card from config.txt comments...")
        
        # Read all lines from config.txt
        for line in self.config.lines:
            stripped_line = line.strip()
            
            # Look for HiFiBerry card comment lines
            if stripped_line.startswith(HIFIBERRY_CARD_COMMENT_PREFIX):
                # Extract the card name after the colon
                try:
                    # Split on the comment prefix and get the part after it
                    card_name = stripped_line.split(HIFIBERRY_CARD_COMMENT_PREFIX, 1)[1].strip()
                    
                    if card_name:
                        logging.info(f"Found card name in config.txt comment: {card_name}")
                        return card_name
                    else:
                        logging.warning("Found HiFiBerry comment but card name is empty")
                        
                except IndexError:
                    logging.warning(f"Malformed HiFiBerry comment line: {stripped_line}")
                    continue
        
        logging.info("No HiFiBerry card comment found in config.txt")
        return None

    def _add_card_comment_before_overlay(self, overlay_name):
        """
        Add HiFiBerry card comment directly before the specified overlay line
        
        Args:
            overlay_name: The full overlay name (e.g., "hifiberry-dacplus-std")
        """
        overlay_line = f"dtoverlay={overlay_name}"
        
        # Find the overlay line and insert comment before it
        for i, line in enumerate(self.config.lines):
            if line.strip() == overlay_line:
                # Insert the comment line before the overlay
                comment_line = f"{HIFIBERRY_CARD_COMMENT_PREFIX} {self.detected_card}\n"
                self.config.lines.insert(i, comment_line)
                logging.debug(f"Added card comment before overlay at line {i + 1}")
                return
        
        # If overlay line not found, log warning
        logging.warning(f"Could not find overlay line '{overlay_line}' to add comment before it")

    def _run_command(self, command):
        try:
            result = subprocess.check_output(
                command, shell=True, stderr=subprocess.DEVNULL, text=True
            ).strip()
            return result
        except subprocess.CalledProcessError:
            return ""

    def _get_card_name(self, overlay, hat_product=None, no_hat_only=False):
        """
        Get the appropriate card name, prioritizing HAT info over overlay mapping
        
        Args:
            overlay: Overlay name (e.g., "dacplusadcpro")
            hat_product: HAT product name from EEPROM (e.g., "DAC+ ADC Pro")
            no_hat_only: If True, prefer cards without hat_name when using overlay mapping
            
        Returns:
            Card name - HAT product name if available, otherwise overlay mapping result
        """
        # If we have valid HAT product info, use it directly
        if hat_product and hat_product.strip():
            logging.info(f"Using HAT product name directly: {hat_product}")
            return hat_product
        
        # Fall back to overlay mapping if no HAT info
        logging.info(f"No HAT product info, using overlay mapping for: {overlay}")
        return self._overlay_to_card_name(overlay, no_hat_only=no_hat_only)

    def _overlay_to_card_name(self, overlay, no_hat_only=False):
        """
        Map overlay name to proper card name(s) from SOUND_CARD_DEFINITIONS
        
        Args:
            overlay: Overlay name (e.g., "dacplusdsp")
            no_hat_only: If True, prefer cards without hat_name, but fall back to HAT cards if none found
            
        Returns:
            String with all matching card names separated by "/" if multiple cards use the same overlay,
            or single card name if only one match, or overlay name if not found
        """
        # Import here to avoid circular imports
        from configurator.soundcard import SOUND_CARD_DEFINITIONS
        
        # Handle overlay names with parameters (e.g., "amp100,automute")
        base_overlay = overlay.split(',')[0] if ',' in overlay else overlay
        
        # Look through all card definitions to find matching dtoverlay
        all_matching_cards = []
        no_hat_cards = []
        
        for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
            dtoverlay = attributes.get("dtoverlay", "")
            if dtoverlay:
                # Extract base overlay name from dtoverlay (remove hifiberry- prefix)
                if dtoverlay.startswith("hifiberry-"):
                    overlay_base = dtoverlay.replace("hifiberry-", "").split(',')[0]
                    if overlay_base == base_overlay:
                        all_matching_cards.append(card_name)
                        
                        # Check if this card has no hat_name
                        hat_name = attributes.get("hat_name")
                        if hat_name is None:
                            no_hat_cards.append(card_name)
        
        # Determine which cards to use
        if no_hat_only:
            if no_hat_cards:
                # Prefer cards without hat_name
                matching_cards = no_hat_cards
                filter_info = " (no HAT cards only)"
            else:
                # Fall back to all cards if no cards without hat_name found
                matching_cards = all_matching_cards
                filter_info = " (fallback to HAT cards)"
        else:
            # Use all matching cards
            matching_cards = all_matching_cards
            filter_info = ""
        
        if matching_cards:
            # Return all matching cards separated by "/"
            result = "/".join(matching_cards)
            logging.info(f"Mapped overlay '{overlay}' to card(s): {result}{filter_info}")
            return result
        else:
            # If no match found, return the overlay name as fallback
            logging.warning(f"No card name found for overlay '{overlay}', using overlay name")
            return overlay

    def detect_card(self):
        logging.info("Detecting HiFiBerry sound card...")
        
        # Check if HAT EEPROM has valid info with retry
        hat_info = None
        hat_card = None
        has_hat_info = False
        
        # Retry HAT detection up to specified number of times with delay (for boot-time reliability)
        for attempt in range(self.hat_attempts):
            try:
                hat_info = get_hat_info(verbose=True)  # Enable verbose for detailed error info
                hat_card = hat_info.get("product")
                has_hat_info = hat_card is not None
                
                if has_hat_info:
                    logging.info(f"HAT detection successful on attempt {attempt + 1}")
                    self._log_hifiberry_event(f"HAT EEPROM read successful on attempt {attempt + 1}: {hat_card}")
                    break
                else:
                    reason = "HAT info returned None/empty product field"
                    if hat_info:
                        reason = f"HAT info: vendor={hat_info.get('vendor')}, product={hat_info.get('product')}, uuid={hat_info.get('uuid')}"
                    logging.warning(f"HAT detection attempt {attempt + 1} failed: {reason}")
                    self._log_hifiberry_event(f"HAT detection attempt {attempt + 1} failed: {reason}")
                    
            except Exception as e:
                error_reason = f"HAT detection exception: {str(e)}"
                logging.warning(f"HAT detection attempt {attempt + 1} failed: {error_reason}")
                self._log_hifiberry_event(f"HAT detection attempt {attempt + 1} failed: {error_reason}")
                hat_info = {"vendor": None, "product": None, "uuid": None}
                
            if attempt < self.hat_attempts - 1:  # Don't sleep on the last attempt
                logging.debug(f"Retrying HAT detection in 1 second...")
                time.sleep(1)
        
        # Final status
        if not has_hat_info:
            final_reason = "All HAT detection attempts failed"
            logging.warning(final_reason)
            self._log_hifiberry_event(final_reason)
        
        # Try HAT info detection first
        logging.info(f"Retrieved HAT info: {hat_info}")
        detected_overlay = self._map_hat_to_overlay(hat_card)
        if detected_overlay and self._validate_detected_card(detected_overlay):
            self.detected_overlay = detected_overlay
            self.detected_card = self._get_card_name(detected_overlay, hat_product=hat_card, no_hat_only=False)
            self._log_hifiberry_event(f"Detected sound card: {self.detected_card} (via HAT EEPROM)")
            return  # Successfully detected and validated

        # Try I2C probing second
        i2c_result = self._probe_i2c()
        if i2c_result:
            # Handle tuple return for special cases (overlay, card_name) or just overlay
            if isinstance(i2c_result, tuple):
                detected_overlay, detected_card_name = i2c_result
            else:
                detected_overlay = i2c_result
                detected_card_name = None
                
            if self._validate_detected_card(detected_overlay):
                self.detected_overlay = detected_overlay
                if detected_card_name:
                    # Use the specific card name provided by I2C detection
                    self.detected_card = detected_card_name
                    logging.info(f"Using I2C-provided card name: {detected_card_name}")
                else:
                    # Use standard card name resolution
                    self.detected_card = self._get_card_name(detected_overlay, hat_product=hat_card, no_hat_only=not has_hat_info)
                self._log_hifiberry_event(f"Detected sound card: {self.detected_card} (via I2C probing)")
                return  # Successfully detected and validated

        # Try aplay detection as fallback
        found = self._run_command("aplay -l | grep hifiberry | grep -v pcm5102")
        if found:
            logging.info(f"Found HiFiBerry card via aplay: {found}")
            detected_overlay = self._map_aplay_to_overlay(found)
            if detected_overlay and self._validate_detected_card(detected_overlay):
                # Use no_hat_only if no HAT info was found
                self.detected_overlay = detected_overlay
                self.detected_card = self._get_card_name(detected_overlay, hat_product=hat_card, no_hat_only=not has_hat_info)
                self._log_hifiberry_event(f"Detected sound card: {self.detected_card} (via aplay)")
                return  # Successfully detected and validated
            else:
                logging.warning(f"Detected overlay {detected_overlay} failed validation, trying other methods")

        # If aplay detection failed, try DSP detection as final fallback
        detected_overlay = self._probe_dsp()
        if detected_overlay and self._validate_detected_card(detected_overlay):
            self.detected_overlay = detected_overlay
            self.detected_card = self._get_card_name(detected_overlay, hat_product=hat_card, no_hat_only=not has_hat_info)
            self._log_hifiberry_event(f"Detected sound card: {self.detected_card} (via DSP detection)")
            return  # Successfully detected and validated

        # If all detection methods failed, leave as None (fallback will be handled elsewhere)
        self.detected_overlay = None
        self.detected_card = None
        self._log_hifiberry_event("No sound card detected (all detection methods failed)")

    def _map_aplay_to_overlay(self, aplay_output):
        """
        Map aplay output to sound card overlay name
        
        Args:
            aplay_output: Raw aplay -l output line
            
        Returns:
            Sound card overlay name or None if not recognized
        """
        logging.info(f"Mapping aplay output: {aplay_output}")
        
        # Common patterns in aplay output for HiFiBerry cards
        aplay_patterns = {
            "snd_rpi_hifiberry_dac": "dacplus-std",
            "snd_rpi_hifiberry_dacplus": "dacplus-std", 
            "snd_rpi_hifiberry_dacplusadc": "dacplusadc",
            "snd_rpi_hifiberry_dacplusadcpro": "dacplusadcpro",
            "snd_rpi_hifiberry_dacplushd": "dacplushd",
            "snd_rpi_hifiberrydacplusdsp": "dacplusdsp",
            "snd_rpi_hifiberry_digi": "digi",
            "snd_rpi_hifiberry_amp": "amp",
            "snd_rpi_hifiberry_amp100": "amp100",
            "snd_rpi_hifiberry_amp3": "amp3",
            "snd_rpi_hifiberry_amp4pro": "amp4pro",
            "snd_rpi_hifiberry_dac8x": "dac8x",
        }
        
        # Check each pattern against the aplay output (case insensitive)
        aplay_lower = aplay_output.lower()
        for pattern, overlay in aplay_patterns.items():
            if pattern in aplay_lower:
                logging.info(f"Matched pattern '{pattern}' -> overlay '{overlay}'")
                return overlay
        
        # If no specific pattern matches, try to extract generic info
        if "dacplusdsp" in aplay_lower or "dsp" in aplay_lower:
            logging.info("Detected DSP-related card from aplay output")
            return "dacplusdsp"
        elif "dacplusadcpro" in aplay_lower:
            logging.info("Detected DAC+ ADC Pro from aplay output")
            return "dacplusadcpro"
        elif "dacplusadc" in aplay_lower:
            logging.info("Detected DAC+ ADC from aplay output")
            return "dacplusadc"
        elif "dacplus" in aplay_lower:
            logging.info("Detected DAC+ related card from aplay output")
            return "dacplus-std"
        elif "digi" in aplay_lower:
            logging.info("Detected Digi card from aplay output")
            return "digi"
        elif "amp" in aplay_lower:
            logging.info("Detected Amp card from aplay output")
            return "amp"
        
        logging.warning(f"Could not map aplay output to known sound card: {aplay_output}")
        return None

    def _map_hat_to_overlay(self, hat_card):
        card_map = {
            "Amp100": "amp100,automute",
            "DAC+ ADC Pro": "dacplusadcpro",
            "DAC+ ADC": "dacplusadc",
            "DAC2 ADC Pro": "dacplusadcpro",
            "DAC2 Pro": "dacplus-pro",
            "DAC 2 HD": "dacplushd",
            "Digi2 Pro": "digi-pro",
            "Amp3": "amp3",
            "Amp4 Pro": "amp4pro",
            "Amp4": "dacplus-std",
            "DAC8x": "dac8x",
            "StudioDAC8x": "dac8x",
            "DAC+ DSP": "dacplusdsp",
            "Digi Pro": "digi-pro",
        }
        logging.info(f"Mapping HAT card: {hat_card}")
        return card_map.get(hat_card)

    def _probe_i2c(self):
        logging.info("Probing I2C for sound card...")
        self.config.enable_i2c()
        self.config.save()

        i2c_checks = [
            ("0x4a 25", "0x07", "dacplusadcpro", None),
            ("0x3b 1", "0x88", "digi", None),
            ("0x4d 40", "0x02", "dacplus-std", None),
            ("0x1b 0", "0x6c", "amp", None),
            ("0x1b 0", "0x60", "amp", None),
            ("0x62 17", "0x8c", "dacplushd", None),
            ("0x60 2", "0x03", "dac", "Beocreate 4CA"),
        ]

        for address, expected, overlay, card_name in i2c_checks:
            result = self._run_command(f"i2cget -f -y 1 {address} 2>/dev/null")
            if result == expected:
                if card_name:
                    # Return tuple (overlay, card_name) for special cases like Beocreate
                    return (overlay, card_name)
                else:
                    # Return just overlay for standard cases
                    return overlay

        logging.warning("No I2C-enabled sound card detected.")
        return None

    def _probe_dsp(self):
        """
        Probe for DSP hardware as a fallback detection method
        
        Returns:
            Sound card overlay name if DSP detected, None otherwise
        """
        logging.info("Probing for DSP hardware...")
        try:
            dsp_info = detect_dsp(timeout=2.0)  # Use shorter timeout for detection
            if dsp_info and dsp_info.get("status") == "detected":
                detected_dsp = dsp_info.get("detected_dsp", "")
                logging.info(f"Detected DSP: {detected_dsp}")
                
                # Check if it's an ADAU14xx DSP (DAC+DSP)
                if "ADAU14" in detected_dsp:
                    logging.info("ADAU14xx DSP detected, identifying as DAC+DSP")
                    return "dacplusdsp"
                else:
                    logging.info(f"Unknown DSP type: {detected_dsp}")
                    return None
            else:
                logging.debug("No DSP detected or DSP service unavailable")
                return None
        except Exception as e:
            logging.debug(f"DSP detection failed: {e}")
            return None

    def _validate_detected_card(self, card_overlay):
        """
        Apply additional validation tests to the detected sound card
        
        Args:
            card_overlay: The detected sound card overlay name
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        if not card_overlay:
            return False
            
        # Check if there's a validation test for this card type
        validation_test = SOUND_CARD_VALIDATION_TESTS.get(card_overlay)
        if validation_test:
            logging.info(f"Running additional validation for {card_overlay}")
            try:
                result = validation_test()
                if not result:
                    logging.warning(f"Validation failed for {card_overlay}")
                    return False
                else:
                    logging.info(f"Validation passed for {card_overlay}")
                    return True
            except Exception as e:
                logging.error(f"Validation test error for {card_overlay}: {e}")
                return False
        else:
            # No additional validation needed
            logging.debug(f"No additional validation required for {card_overlay}")
            return True

    def configure_card(self, load_overlay=False, reboot_on_change=False):
        if not self.detected_overlay:
            logging.error("No sound card detected to configure.")
            return

        # Check if the same overlay is already configured
        expected_overlay = f"hifiberry-{self.detected_overlay}"
        
        # Check current overlays in config.txt
        current_hifiberry_overlays = []
        for line in self.config.lines:
            stripped_line = line.strip()
            if stripped_line.startswith("dtoverlay=hifiberry"):
                # Extract the overlay name
                overlay_part = stripped_line.replace("dtoverlay=", "")
                current_hifiberry_overlays.append(overlay_part)
        
        # Check if the expected overlay is already present
        overlay_already_configured = expected_overlay in current_hifiberry_overlays
        
        if overlay_already_configured:
            logging.info(f"Card {self.detected_card} is already configured with overlay {expected_overlay}")
            
            # Still update the comment even if overlay is already configured
            self._remove_hifiberry_comments()
            self._add_card_comment_before_overlay(expected_overlay)
            self.config.save()
            
            logging.info("Updated HiFiBerry card comment in config.txt")
            config_changed = False
        else:
            # Check if any other HiFiBerry overlay is configured
            if current_hifiberry_overlays:
                logging.info(f"Found existing HiFiBerry overlays: {current_hifiberry_overlays}")
                logging.info(f"Replacing with detected card: {self.detected_card}")
            else:
                logging.info(f"No existing HiFiBerry overlays found")
                logging.info(f"Adding overlay for detected card: {self.detected_card}")

            logging.info(f"Configuring card: {self.detected_card} (overlay: {self.detected_overlay})")
            self.config.remove_hifiberry_overlays()
            self._remove_hifiberry_comments()
            
            # Enable overlay first, then add comment before it
            self.config.enable_overlay(expected_overlay)
            self._add_card_comment_before_overlay(expected_overlay)

            if self.eeprom == 0:
                self.config.disable_eeprom()

            self.config.save()
            config_changed = True
            
            # Log overlay configuration to HiFiBerry log
            self._log_hifiberry_event(f"Overlay written to config.txt: {expected_overlay}")
            
            with open(self.reboot_file, "w") as reboot_file:
                reboot_file.write(f"Configuring {self.detected_card} requires a reboot.\n")
        
        # Load overlay directly if requested
        if load_overlay:
            self._load_overlay_directly(expected_overlay)
            
        # Reboot if config.txt was changed and reboot_on_change is True
        if config_changed and reboot_on_change:
            logging.info("Config.txt was changed, rebooting system...")
            self._log_hifiberry_event("System reboot initiated due to config.txt changes")
            try:
                subprocess.run(["systemctl", "reboot"], check=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to reboot system: {e}")
            except Exception as e:
                logging.error(f"Error during reboot: {e}")

    def _load_overlay_directly(self, overlay_name):
        """
        Load the device tree overlay directly using dtoverlay command
        
        Args:
            overlay_name: Full overlay name (e.g., "hifiberry-dacplus-std")
        """
        try:
            # Remove "hifiberry-" prefix for dtoverlay command
            if overlay_name.startswith("hifiberry-"):
                dtoverlay_name = overlay_name.replace("hifiberry-", "")
            else:
                dtoverlay_name = overlay_name
            
            # Handle overlay parameters (e.g., "amp100,automute" -> "amp100 automute")
            if "," in dtoverlay_name:
                parts = dtoverlay_name.split(",")
                dtoverlay_name = parts[0]
                params = " ".join(parts[1:])
                cmd = f"dtoverlay {dtoverlay_name} {params}"
            else:
                cmd = f"dtoverlay {dtoverlay_name}"
            
            logging.info(f"Loading overlay directly: {cmd}")
            result = self._run_command(cmd)
            
            if result == "" or "dtoverlay" in result.lower():
                # dtoverlay typically doesn't output anything on success
                logging.info(f"Successfully loaded overlay: {dtoverlay_name}")
            else:
                logging.warning(f"dtoverlay command output: {result}")
                
        except Exception as e:
            logging.error(f"Failed to load overlay {overlay_name}: {str(e)}")

    def detect_and_configure(self, store=False, fallback_dac=False, load_overlay=False, reboot_on_change=False):
        self.detect_card()
        
        # If no card detected and fallback_dac is True, assume DAC+ Light
        if not self.detected_card and fallback_dac:
            logging.info("No card detected, assuming DAC+ Light as fallback")
            self.detected_overlay = "dac"  # DAC+ Light uses hifiberry-dac overlay
            self.detected_card = "DAC+ Light"  # Set directly to avoid mapping confusion
            logging.info(f"Fallback card: {self.detected_card} (overlay: {self.detected_overlay})")
            self._log_hifiberry_event(f"Detected sound card: {self.detected_card} (fallback)")
        
        if store:
            self.configure_card(load_overlay=load_overlay, reboot_on_change=reboot_on_change)
        else:
            # Output the proper card name
            if self.detected_card:
                logging.info(f"Detected card: {self.detected_card} (overlay: {self.detected_overlay})")
                # Print just the card name for command-line output
                print(self.detected_card)
            else:
                logging.info("No sound card detected")
                self._log_hifiberry_event("No sound card detected (detection output)")
                print("Unknown")

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="HiFiBerry Sound Card Detector")
    parser.add_argument("--store", action="store_true", help="Store detected card configuration in config.txt")
    parser.add_argument("--fallback-dac", action="store_true", help="Assume DAC+ Light if no card is detected")
    parser.add_argument("--dtoverlay", action="store_true", help="Load the overlay directly with dtoverlay command after configuring config.txt")
    parser.add_argument("--reboot", action="store_true", help="Reboot the system if config.txt has been changed")
    parser.add_argument("--logfile", type=str, help="Log HiFiBerry events to specified file (with timestamps)")
    args = parser.parse_args()

    detector = SoundcardDetector(hifiberry_log_file=args.logfile)
    detector.detect_and_configure(
        store=args.store, 
        fallback_dac=getattr(args, 'fallback_dac'), 
        load_overlay=args.dtoverlay,
        reboot_on_change=args.reboot
    )

if __name__ == "__main__":
    main()


