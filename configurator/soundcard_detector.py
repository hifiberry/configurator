#!/usr/bin/env python3

import os
import subprocess
import logging
import argparse
from configurator.configtxt import ConfigTxt
from configurator.hattools import get_hat_info  # Import the get_hat_info module
from configurator.dsptoolkit import detect_dsp
from configurator.soundcard import Soundcard

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
    def __init__(self, config_file="/boot/firmware/config.txt", reboot_file="/tmp/reboot"):
        self.config = ConfigTxt(config_file)
        self.reboot_file = reboot_file
        self.detected_card = None  # Card name (e.g., "DAC+ DSP")
        self.detected_overlay = None  # Overlay name (e.g., "dacplusdsp")
        self.eeprom = 1

    def _run_command(self, command):
        try:
            result = subprocess.check_output(
                command, shell=True, stderr=subprocess.DEVNULL, text=True
            ).strip()
            return result
        except subprocess.CalledProcessError:
            return ""

    def _overlay_to_card_name(self, overlay):
        """
        Map overlay name to proper card name from SOUND_CARD_DEFINITIONS
        
        Args:
            overlay: Overlay name (e.g., "dacplusdsp")
            
        Returns:
            Card name (e.g., "DAC+ DSP") or overlay name if not found
        """
        # Import here to avoid circular imports
        from configurator.soundcard import SOUND_CARD_DEFINITIONS
        
        # Handle overlay names with parameters (e.g., "amp100,automute")
        base_overlay = overlay.split(',')[0] if ',' in overlay else overlay
        
        # Look through all card definitions to find matching dtoverlay
        for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
            dtoverlay = attributes.get("dtoverlay", "")
            if dtoverlay:
                # Extract base overlay name from dtoverlay (remove hifiberry- prefix)
                if dtoverlay.startswith("hifiberry-"):
                    overlay_base = dtoverlay.replace("hifiberry-", "").split(',')[0]
                    if overlay_base == base_overlay:
                        return card_name
        
        # If no match found, return the overlay name as fallback
        logging.warning(f"No card name found for overlay '{overlay}', using overlay name")
        return overlay

    def detect_card(self):
        logging.info("Detecting HiFiBerry sound card...")
        found = self._run_command("aplay -l | grep hifiberry | grep -v pcm5102")

        if not found:
            # Use the imported get_hat_info function (silent mode for detection)
            hat_info = get_hat_info(verbose=False)
            hat_card = hat_info.get("product")
            logging.info(f"Retrieved HAT info: {hat_info}")
            detected_overlay = self._map_hat_to_overlay(hat_card)
            if detected_overlay and self._validate_detected_card(detected_overlay):
                self.detected_overlay = detected_overlay
                self.detected_card = self._overlay_to_card_name(detected_overlay)
            else:
                detected_overlay = self._probe_i2c()
                if detected_overlay and self._validate_detected_card(detected_overlay):
                    self.detected_overlay = detected_overlay
                    self.detected_card = self._overlay_to_card_name(detected_overlay)
                else:
                    # Try DSP detection as final fallback
                    detected_overlay = self._probe_dsp()
                    if detected_overlay and self._validate_detected_card(detected_overlay):
                        self.detected_overlay = detected_overlay
                        self.detected_card = self._overlay_to_card_name(detected_overlay)
        else:
            logging.info(f"Found HiFiBerry card via aplay: {found}")
            detected_overlay = self._map_aplay_to_overlay(found)
            if detected_overlay and self._validate_detected_card(detected_overlay):
                self.detected_overlay = detected_overlay
                self.detected_card = self._overlay_to_card_name(detected_overlay)
            else:
                logging.warning(f"Detected overlay {detected_overlay} failed validation")
                self.detected_overlay = None
                self.detected_card = None

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
            "snd_rpi_hifiberry_beocreate": "beo",
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
            ("0x4a 25", "0x07", "dacplusadcpro"),
            ("0x3b 1", "0x88", "digi"),
            ("0x4d 40", "0x02", "dacplus-std"),
            ("0x1b 0", "0x6c", "amp"),
            ("0x1b 0", "0x60", "amp"),
            ("0x62 17", "0x8c", "dacplushd"),
            ("0x60 2", "0x03", "beo"),
        ]

        for address, expected, card in i2c_checks:
            result = self._run_command(f"i2cget -y 1 {address} 2>/dev/null")
            if result == expected:
                return card

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

    def configure_card(self):
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
        if expected_overlay in current_hifiberry_overlays:
            logging.info(f"Card {self.detected_card} is already configured with overlay {expected_overlay}")
            logging.info("No changes needed to config.txt")
            return
        
        # Check if any other HiFiBerry overlay is configured
        if current_hifiberry_overlays:
            logging.info(f"Found existing HiFiBerry overlays: {current_hifiberry_overlays}")
            logging.info(f"Replacing with detected card: {self.detected_card}")
        else:
            logging.info(f"No existing HiFiBerry overlays found")
            logging.info(f"Adding overlay for detected card: {self.detected_card}")

        logging.info(f"Configuring card: {self.detected_card} (overlay: {self.detected_overlay})")
        self.config.remove_hifiberry_overlays()
        self.config.enable_overlay(expected_overlay)

        if self.eeprom == 0:
            self.config.disable_eeprom()

        self.config.save()
        with open(self.reboot_file, "w") as reboot_file:
            reboot_file.write(f"Configuring {self.detected_card} requires a reboot.\n")

    def detect_and_configure(self, store=False):
        self.detect_card()
        if store:
            self.configure_card()
        else:
            # Output the proper card name
            if self.detected_card:
                logging.info(f"Detected card: {self.detected_card} (overlay: {self.detected_overlay})")
                # Print just the card name for command-line output
                print(self.detected_card)
            else:
                logging.info("No sound card detected")
                print("Unknown")

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="HiFiBerry Sound Card Detector")
    parser.add_argument("--store", action="store_true", help="Store detected card configuration in config.txt")
    args = parser.parse_args()

    detector = SoundcardDetector()
    detector.detect_and_configure(store=args.store)

if __name__ == "__main__":
    main()


