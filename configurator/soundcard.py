import subprocess
import logging
import argparse
import sys
import tempfile
import os
try:
    import argcomplete
    ARGCOMPLETE_AVAILABLE = True
except ImportError:
    ARGCOMPLETE_AVAILABLE = False

# Import the get_hat_info function from hattools
from configurator.hattools import get_hat_info

# Constants
UNKNOWN_CARD_NAME = "Unknown"

# ALSA state file template for creating dummy mixer controls
ALSA_STATE_FILE_TEMPLATE = """
state.sndrpihifiberry {
    control.98 {
        iface MIXER
        name '%CONTROL_NAME%'
        value.0 255
        value.1 255
        comment {
            access 'read write user'
            type INTEGER
            count 2
            range '0 - 255'
            tlv '0000000100000008ffffdcc400000023'
            dbmin -9020
            dbmax -95
            dbvalue.0 -95
            dbvalue.1 -95
        }
    }
}
"""

# Sound card definitions as a constant dictionary
SOUND_CARD_DEFINITIONS = {
    "DAC8x/ADC8x": {
        "aplay_contains": "DAC8xADC8x",
        "hat_name": "DAC8x",
        "volume_control": None,
        "output_channels": 8,
        "input_channels": 8,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC", "ADC"],
        "dtoverlay": "hifiberry-dac8x",
        "is_pro": False,
    },
    "DAC8x": {
        "aplay_contains": "DAC8x",
        "hat_name": "DAC8x",
        "volume_control": None,
        "output_channels": 8,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dac8x",
        "is_pro": False,
    },
    "Digi2 Pro": {
        "hat_name": "Digi2 Pro",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp"],
        "supports_dsp": True,
        "card_type": ["Digi"],
        "dtoverlay": "hifiberry-digi-pro",
        "is_pro": True,
    },
    "Amp100": {
        "hat_name": "Amp100",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["spdifnoclock", "toslink"],
        "supports_dsp": False,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-amp100,automute",
        "is_pro": True,
    },
    "Amp3": {
        "aplay_contains": "Amp3",
        "hat_name": "Amp3",
        "volume_control": "A.Mstr Vol",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": False,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-amp3",
        "is_pro": False,
    },
    "Amp4": {
        "hat_name": "Amp4",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": True,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-dacplus-std",
        "is_pro": False,
    },
    "Amp4 Pro": {
        "aplay_contains": "Amp4 Pro",
        "hat_name": "Amp4 Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": True,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-amp4pro",
        "is_pro": True,
    },
    "DAC+ ADC Pro": {
        "aplay_contains": "DAC+ADC Pro",
        "hat_name": "DAC+ ADC Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": False,
        "card_type": ["DAC", "ADC"],
        "dtoverlay": "hifiberry-dacplusadcpro",
        "is_pro": True,
    },
    "DAC+ ADC": {
        "aplay_contains": "DAC+ ADC",
        "hat_name": "DAC+ ADC",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": False,
        "card_type": ["DAC", "ADC"],
        "dtoverlay": "hifiberry-dacplusadc",
        "is_pro": False,
    },
    "DAC2 ADC Pro": {
        "aplay_contains": "DAC2 ADC Pro",
        "hat_name": "DAC2 ADC Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": True,
        "card_type": ["DAC", "ADC"],
        "dtoverlay": "hifiberry-dacplusadcpro",
        "is_pro": True,
    },
    "DAC2 HD": {
        "aplay_contains": "DAC+ HD",
        "hat_name": "DAC 2 HD",
        "volume_control": "DAC",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": True,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dacplushd",
        "is_pro": True,
        "aliases": ["DAC2 HD","DAC 2 HD"," DAC2HD"],
    },
    "DAC+ DSP": {
        "aplay_contains": "DAC+DSP",
        "hat_name": "DAC+ DSP",
        "volume_control": "DSPVolume",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["toslink"],
        "supports_dsp": True,
        "card_type": ["DAC", "Digi"],
        "dtoverlay": "hifiberry-dacplusdsp",
        "is_pro": True,
    },
    "DAC+/Amp2": {
        "aplay_contains": "DAC+",
        "hat_name": None,
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dacplus-std",
        "is_pro": False,
    },
    "DAC+ Pro": {
        "aplay_contains": "DAC+ Pro",
        "hat_name": "DAC+ Pro", 
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dacplus-pro",
        "is_pro": True,
    },
    "DAC2 Pro": {
        "hat_name": "DAC2 Pro",
        "volume_control": "Digital",
        "headphone_volume_control": "Headphone",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": True,
        "card_type": ["DAC", "Headphone"],
        "dtoverlay": "hifiberry-dacplus-pro",
        "is_pro": True,
    },
    "Amp+": {
        "aplay_contains": "AMP",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-amp",
        "is_pro": False,
    },
    "Digi+ Pro": {
        "aplay_contains": "Digi Pro",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["digi"],
        "supports_dsp": True,
        "card_type": ["Digi"],
        "dtoverlay": "hifiberry-digi-pro",
        "is_pro": True,
    },
    "Digi+": {
        "aplay_contains": "Digi",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["digi"],
        "supports_dsp": False,
        "card_type": ["Digi"],
        "dtoverlay": "hifiberry-digi",
        "is_pro": False,
    },
    "Beocreate 4-Channel Amplifier": {
        "aplay_contains": "beocreate",
        "hat_name": "Beocreate 4-Channel Amplifier",
        "aliases": ["Beocreate 4CA"],
        "volume_control": "DSPVolume",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp", "toslink"],
        "supports_dsp": True,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-dac",
        "is_pro": True,
    },
    "DAC+ Light": {
        "aplay_contains": "snd_rpi_hifiberry_dac",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dac",
        "is_pro": False,
    },
    "DAC+ Zero": {
        "aplay_contains": "snd_rpi_hifiberry_dac",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dac",
        "is_pro": False,
    },
    "MiniAmp": {
        "aplay_contains": "snd_rpi_hifiberry_dac",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-dac",
        "is_pro": False,
    },
    "ADC": {
        "aplay_contains": None,
        "hat_name": "ADC",
        "volume_control": None,
        "output_channels": 0,
        "input_channels": 2,
        "features": [],
        "supports_dsp": False,
        "card_type": ["ADC"],
        "dtoverlay": "hifiberry-adc",
        "is_pro": False,
    },
    "HDMI Audio": {
        "aplay_contains": None,
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["Digi"],
        "dtoverlay": None,
        "is_pro": False,
        "aliases": ["HDMI"],
    },
    "Null": {
        "aplay_contains": None,
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["Null"],
        "dtoverlay": None,
        "is_pro": False,
    },
}


def list_all_sound_cards(output_format="table"):
    """
    List all available HiFiBerry sound cards with their device tree overlays.
    
    Args:
        output_format: Output format - "table" or "csv"
    """
    if output_format == "csv":
        # CSV format output
        print("Name,DT Overlay,Volume Control,Output Channels,Input Channels,Features,Supports DSP,Card Type")
        for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
            dtoverlay = attributes.get("dtoverlay", "unknown")
            volume_control = attributes.get("volume_control") or ""
            features = ";".join(attributes.get("features", []))
            card_types = ";".join(attributes.get("card_type", []))
            supports_dsp = "Yes" if attributes.get("supports_dsp", False) else "No"
            
            print(f'"{card_name}","{dtoverlay}","{volume_control}",'
                  f'{attributes.get("output_channels", 0)},{attributes.get("input_channels", 0)},'
                  f'"{features}","{supports_dsp}","{card_types}"')
    
    else:
        # Table format (default)
        print("Available HiFiBerry Sound Cards:")
        print("=" * 70)
        print(f"{'Sound Card Name':<30} {'Device Tree Overlay':<30}")
        print("-" * 70)
        
        for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
            dtoverlay = attributes.get("dtoverlay", "unknown")
            print(f"{card_name:<30} {dtoverlay:<30}")
        
        print("-" * 70)
        print(f"Total: {len(SOUND_CARD_DEFINITIONS)} sound cards")


class Soundcard:
    def __init__(
        self,
        name=None,
        volume_control=None,
        headphone_volume_control=None,
        output_channels=2,
        input_channels=0,
        features=None,
        hat_name=None,
        supports_dsp=False,
        card_type=None,
        no_eeprom=False,
        prioritize_aplay=False,
    ):
        if name is None:
            if prioritize_aplay:
                detected_card = self._detect_card_aplay_priority(no_eeprom=no_eeprom)
            else:
                detected_card = self._detect_card(no_eeprom=no_eeprom)
                
            if detected_card:
                self.name = detected_card["name"]
                self.volume_control = detected_card.get("volume_control")
                self.headphone_volume_control = detected_card.get("headphone_volume_control")
                self.output_channels = detected_card.get("output_channels", 2)
                self.input_channels = detected_card.get("input_channels", 0)
                self.features = detected_card.get("features", [])
                self.hat_name = detected_card.get("hat_name")
                self.supports_dsp = detected_card.get("supports_dsp", False)
                self.card_type = detected_card.get("card_type", [])
            else:
                self.name = UNKNOWN_CARD_NAME
                self.volume_control = volume_control
                self.headphone_volume_control = headphone_volume_control
                self.output_channels = output_channels
                self.input_channels = input_channels
                self.features = features or []
                self.hat_name = hat_name
                self.supports_dsp = supports_dsp
                self.card_type = card_type or []
        else:
            self.name = name
            self.volume_control = volume_control
            self.headphone_volume_control = headphone_volume_control
            self.output_channels = output_channels
            self.input_channels = input_channels
            self.features = features or []
            self.hat_name = hat_name
            self.supports_dsp = supports_dsp
            self.card_type = card_type or []

    def __str__(self):
        return (
            f"Soundcard(name={self.name}, volume_control={self.volume_control}, "
            f"headphone_volume_control={self.headphone_volume_control}, "
            f"output_channels={self.output_channels}, input_channels={self.input_channels}, "
            f"features={self.features}, hat_name={self.hat_name}, supports_dsp={self.supports_dsp}, "
            f"card_type={self.card_type})"
        )

    def _additional_card_checks(self, aplay_output, initial_detection):
        """
        Perform additional checks to refine sound card detection based on aplay output
        and hardware-specific features.
        
        Args:
            aplay_output: Output from aplay -l command
            initial_detection: Initial card detection result from pattern matching
            
        Returns:
            Refined card detection result or original if no refinement needed
        """
        if not initial_detection:
            return initial_detection
            
        # Check for DAC+ Pro vs DAC2 Pro distinction
        # This handles both direct matches and cases where "DAC+/Amp2" was detected first
        if (initial_detection["name"] in ["DAC+ Pro", "DAC2 Pro", "DAC+/Amp2"] and 
            "dacplus" in aplay_output.lower()):
            return self._distinguish_dac_pro_models(aplay_output, initial_detection)
            
        return initial_detection
    
    def _distinguish_dac_pro_models(self, aplay_output, initial_detection):
        """
        Distinguish between DAC+ Pro and DAC2 Pro based on headphone mixer control.
        
        DAC2 Pro has a 'Headphone' mixer control, DAC+ Pro does not.
        """
        try:
            # First check if this is actually a DAC+ Pro model based on aplay output
            if "HiFiBerry DAC+ Pro" not in aplay_output:
                # If not a DAC+ Pro, return original detection
                return initial_detection
            
            # Extract card number from aplay output
            card_number = None
            for line in aplay_output.split('\n'):
                if 'hifiberry' in line.lower() and 'dacplus' in line.lower():
                    # Parse line like: "card 0: sndrpihifiberry [snd_rpi_hifiberry_dacplus], device 0:"
                    if line.strip().startswith('card '):
                        parts = line.split(':')
                        if len(parts) > 0:
                            card_part = parts[0].strip()
                            if card_part.startswith('card '):
                                try:
                                    card_number = int(card_part.split()[1])
                                    break
                                except (ValueError, IndexError):
                                    continue
            
            if card_number is not None:
                # Check for headphone mixer control
                amixer_output = subprocess.check_output(
                    f"amixer -c {card_number} | grep -i head", 
                    shell=True, text=True
                ).strip()
                
                if "Headphone" in amixer_output:
                    logging.info("Detected DAC2 Pro (has Headphone mixer control)")
                    # Return DAC2 Pro configuration
                    for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                        if card_name == "DAC2 Pro":
                            return {"name": card_name, **attributes}
                else:
                    logging.info("Detected DAC+ Pro (no Headphone mixer control)")
                    # Return DAC+ Pro configuration  
                    for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                        if card_name == "DAC+ Pro":
                            return {"name": card_name, **attributes}
                            
        except subprocess.CalledProcessError:
            logging.debug("Could not run amixer command for DAC Pro distinction")
        except Exception as e:
            logging.debug(f"Error during DAC Pro distinction: {e}")
            
        # If we can't determine, return the initial detection
        return initial_detection

    def _detect_card(self, no_eeprom=False):
        """
        Detect sound card using SoundcardDetector which includes config database override,
        HAT EEPROM, I2C, aplay, and DSP detection.
        
        Returns:
            Dictionary with card attributes or None if not detected
        """
        try:
            from configurator.soundcard_detector import SoundcardDetector
            
            # Use SoundcardDetector for comprehensive detection
            # Enable pcm5102 detection to support DAC+ Zero/Light cards
            detector = SoundcardDetector(include_pcm5102=True)
            detector.detect_card()
            
            # Check if a card was detected
            if detector.detected_card:
                # Handle multiple card names separated by "/"
                detected_cards = detector.detected_card.split("/")
                
                # First try exact name matching for each detected card
                for detected_name in detected_cards:
                    detected_name = detected_name.strip()
                    for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                        if card_name == detected_name:
                            logging.info(f"Detected sound card: {card_name}")
                            return {"name": card_name, **attributes}
                
                # Then try alias matching for each detected card
                for detected_name in detected_cards:
                    detected_name = detected_name.strip()
                    for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                        aliases = attributes.get("aliases", [])
                        if detected_name in aliases:
                            logging.info(f"Detected sound card via alias: {detected_name} -> {card_name}")
                            return {"name": card_name, **attributes}
                
                # If not found in definitions or aliases, log warning and return None
                logging.warning(f"Detected card '{detector.detected_card}' not found in SOUND_CARD_DEFINITIONS or aliases")
                return None
            else:
                logging.warning("No matching sound card detected.")
                return None
                
        except Exception as e:
            logging.error(f"Error during sound card detection: {str(e)}")
            return None

    def _detect_card_aplay_priority(self, no_eeprom=False):
        """
        Detect sound card with aplay -l as the highest priority source.
        
        This method prioritizes the actual loaded ALSA driver from aplay -l output
        over other detection methods, as this represents the real running soundcard.
        First checks config.txt for fixed card comment, then uses additional detection
        methods (HAT EEPROM, I2C) only for disambiguation.
        
        Returns:
            Dictionary with card attributes or None if not detected
        """
        try:
            from configurator.soundcard_detector import SoundcardDetector
            
            # Step 0: Check if there's a fixed card name in config.txt comment
            try:
                detector = SoundcardDetector()
                config_card_name = detector.detect_from_config_txt_comment()
                if config_card_name:
                    # Verify this card exists in our definitions
                    if config_card_name in SOUND_CARD_DEFINITIONS:
                        # Verify that aplay shows a HiFiBerry card is loaded
                        try:
                            aplay_result = subprocess.check_output("aplay -l", shell=True, text=True)
                            if 'hifiberry' in aplay_result.lower():
                                logging.info(f"Using fixed card from config.txt comment: {config_card_name}")
                                return {"name": config_card_name, **SOUND_CARD_DEFINITIONS[config_card_name]}
                        except:
                            pass
                    logging.warning(f"Card '{config_card_name}' from config.txt not found in definitions")
            except Exception as e:
                logging.debug(f"Could not read config.txt comment: {e}")
            
            # Step 1: Get the actual loaded ALSA driver from aplay -l (highest priority)
            detected_overlay = None
            try:
                aplay_result = subprocess.check_output("aplay -l", shell=True, text=True)
                if 'hifiberry' in aplay_result.lower():
                    # Use the SoundcardDetector's aplay mapping to get the overlay
                    detector = SoundcardDetector()
                    # Extract the relevant line with the driver name
                    for line in aplay_result.strip().split('\n'):
                        if 'hifiberry' in line.lower() and '[' in line and ']' in line:
                            detected_overlay = detector._map_aplay_to_overlay(line)
                            if detected_overlay:
                                logging.info(f"Detected overlay from aplay: {detected_overlay}")
                                break
            except Exception as e:
                logging.warning(f"Could not get aplay output: {e}")
            
            # Step 2: If we have an overlay from aplay, use it to get the card definition
            if detected_overlay:
                # Use SoundcardDetector to get additional info (HAT name, etc.) for disambiguation
                detector = SoundcardDetector(include_pcm5102=True)
                detector.detect_card()
                hat_card = None
                has_hat_info = False
                
                # Check if we have HAT info that can help with disambiguation
                try:
                    hat_info = get_hat_info()
                    if hat_info.get('product'):
                        hat_card = hat_info.get('product')
                        has_hat_info = True
                except:
                    pass
                
                # Get the card name based on the overlay, using HAT info if available
                card_name = detector._get_card_name(detected_overlay, hat_product=hat_card, no_hat_only=not has_hat_info)
                
                if card_name:
                    # Try exact match first
                    if card_name in SOUND_CARD_DEFINITIONS:
                        logging.info(f"Detected sound card (aplay priority): {card_name}")
                        return {"name": card_name, **SOUND_CARD_DEFINITIONS[card_name]}
                    
                    # Try alias matching if exact match failed
                    for def_name, attributes in SOUND_CARD_DEFINITIONS.items():
                        aliases = attributes.get('aliases', [])
                        if card_name in aliases:
                            logging.info(f"Detected sound card via alias (aplay priority): {card_name} -> {def_name}")
                            return {"name": def_name, **attributes}
                    
                    # If not found in definitions, log warning
                    logging.warning(f"Card name '{card_name}' from aplay not found in SOUND_CARD_DEFINITIONS")
            
            # Step 3: Fallback to original detection method if aplay didn't work
            logging.info("aplay detection did not yield results, falling back to standard detection")
            return self._detect_card(no_eeprom=no_eeprom)
                
        except Exception as e:
            logging.error(f"Error during aplay-priority sound card detection: {str(e)}")
            # Final fallback to standard detection
            return self._detect_card(no_eeprom=no_eeprom)

    def get_mixer_control_name(self, use_softvol_fallback=False):
        """
        Returns the name of the mixer control for the detected sound card.
        If no mixer control is defined and use_softvol_fallback is True, returns "Softvol".
        Otherwise returns None if no mixer control is defined.
        """
        if self.volume_control:
            return self.volume_control
        elif use_softvol_fallback:
            return "Softvol"
        else:
            return None

    def get_headphone_volume_control_name(self):
        """
        Returns the name of the headphone volume control for the detected sound card.
        Returns None if no headphone volume control is defined.
        """
        return self.headphone_volume_control

    def get_hardware_index(self):
        """
        Returns the hardware index of the detected sound card.
        Uses alsaaudio if available, falls back to parsing aplay -l output.
        Compatible with both pyalsaaudio 0.8 and 0.9+.
        """
        try:
            import alsaaudio
            
            # Check pyalsaaudio version by checking available methods
            # Version 0.9+ uses card_indexes() while 0.8 uses cards()
            if hasattr(alsaaudio, 'card_indexes'):
                # pyalsaaudio 0.9+
                cards = alsaaudio.card_indexes()
                
                # Loop through each card and check if it's a HiFiBerry
                for card_index in cards:
                    try:
                        card_name_result = alsaaudio.card_name(card_index)
                        
                        # Handle different return types from card_name()
                        if isinstance(card_name_result, tuple):
                            # Some versions return a tuple (long_name, short_name)
                            # Use the first element (long name) which is more descriptive
                            card_name = card_name_result[0].lower()
                            logging.debug(f"Card name returned as tuple: {card_name_result}")
                        elif isinstance(card_name_result, str):
                            # Normal case - card_name returns a string
                            card_name = card_name_result.lower()
                        else:
                            # Unknown return type, convert to string first
                            logging.warning(f"Unexpected type from card_name(): {type(card_name_result)}")
                            card_name = str(card_name_result).lower()
                        
                        if 'hifiberry' in card_name:
                            logging.info(f"Found HiFiBerry card at index {card_index}: {card_name}")
                            return card_index
                    except Exception as e:
                        logging.warning(f"Error getting name for card index {card_index}: {str(e)}")
                        continue
            else:
                # pyalsaaudio 0.8
                cards = alsaaudio.cards()
                
                # In 0.8, cards() returns a list of card names
                for i, card_name in enumerate(cards):
                    if 'hifiberry' in card_name.lower():
                        logging.info(f"Found HiFiBerry card at index {i}: {card_name}")
                        return i
            
            # Fall back to shell command if no card was found via alsaaudio
            return self._get_hardware_index_fallback()
        except ImportError:
            logging.warning("alsaaudio module not available, falling back to shell command")
            return self._get_hardware_index_fallback()
    
    def _get_hardware_index_fallback(self):
        """
        Fallback method to get hardware index using shell commands.
        """
        try:
            result = subprocess.check_output("aplay -l", shell=True, text=True)
            lines = result.strip().split('\n')
            for line in lines:
                if 'hifiberry' in line.lower():
                    parts = line.split(':')
                    if len(parts) > 0:
                        card_info = parts[0].strip()
                        if card_info.startswith('card '):
                            try:
                                card_index = int(card_info.split()[1])
                                logging.info(f"Found HiFiBerry card at index {card_index} (fallback method)")
                                return card_index
                            except (ValueError, IndexError):
                                logging.warning(f"Could not parse card index from: {line}")
            
            return None
        except subprocess.CalledProcessError:
            logging.error("Error running aplay -l command")
            return None

    def create_dummy_alsa_control(self, control_name):
        """
        Create a dummy ALSA mixer control using a state file.
        
        This creates a software mixer control that can be used for volume control
        when the sound card doesn't provide hardware volume controls.
        
        Args:
            control_name (str): Name of the mixer control to create
            
        Returns:
            bool: True if the control was created successfully, False otherwise
            
        Raises:
            Exception: If there's an error creating the control
        """
        try:
            # Check if the control already exists
            if self._check_mixer_control_exists(control_name):
                logging.info(f"ALSA mixer control '{control_name}' already exists")
                return True
            
            # Create temporary state file
            with tempfile.NamedTemporaryFile(mode='w', dir="/tmp", delete=False, suffix='.state') as statefile:
                content = ALSA_STATE_FILE_TEMPLATE.replace('%CONTROL_NAME%', control_name)
                logging.debug(f"Creating ALSA state file with content:\n{content}")
                statefile.write(content)
                statefile.flush()
                
                # Apply the state file using alsactl
                command = f"/usr/sbin/alsactl -f {statefile.name} restore"
                logging.debug(f"Running command: {command}")
                
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                
                # Note: alsactl may return non-zero exit codes for warnings, not just errors
                # We should check if the control was actually created rather than just the exit code
                if result.returncode != 0:
                    logging.warning(f"alsactl returned non-zero exit code: {result.stderr}")
                
                # Verify the control was created (this is the definitive test)
                if self._check_mixer_control_exists(control_name):
                    logging.info(f"Successfully created ALSA mixer control '{control_name}'")
                    return True
                else:
                    logging.error(f"ALSA mixer control '{control_name}' was not created")
                    if result.returncode != 0:
                        logging.error(f"alsactl error: {result.stderr}")
                    return False
                    
        except Exception as e:
            logging.error(f"Error creating ALSA mixer control '{control_name}': {str(e)}")
            return False
        finally:
            # Clean up temporary file
            try:
                if 'statefile' in locals():
                    os.unlink(statefile.name)
            except Exception as e:
                logging.warning(f"Could not remove temporary state file: {str(e)}")

    def _check_mixer_control_exists(self, control_name):
        """
        Check if a mixer control exists on the sound card.
        
        Args:
            control_name (str): Name of the mixer control to check
            
        Returns:
            bool: True if the control exists, False otherwise
        """
        try:
            # First try with alsaaudio if available
            try:
                import alsaaudio
                hw_index = self.get_hardware_index()
                if hw_index is not None:
                    mixers = alsaaudio.mixers(cardindex=hw_index)
                    return control_name in mixers
            except ImportError:
                logging.debug("alsaaudio not available, using amixer command")
            
            # Fallback to amixer command
            hw_index = self.get_hardware_index()
            if hw_index is not None:
                result = subprocess.run(
                    f"amixer -c {hw_index} | grep -q '{control_name}'",
                    shell=True,
                    capture_output=True
                )
                return result.returncode == 0
            
            return False
            
        except Exception as e:
            logging.debug(f"Error checking mixer control '{control_name}': {str(e)}")
            return False

    def get_or_create_volume_control(self, preferred_name=None):
        """
        Get the existing volume control or create a dummy one if none exists.
        
        Args:
            preferred_name (str, optional): Preferred name for the volume control.
                                          Defaults to "Softvol" if not specified.
            
        Returns:
            str or None: Name of the volume control, or None if creation failed
        """
        # If the card already has a hardware volume control, use it
        if self.volume_control:
            return self.volume_control
        
        # Determine the control name to create
        control_name = preferred_name or "Softvol"
        
        # Try to create the dummy control
        if self.create_dummy_alsa_control(control_name):
            return control_name
        else:
            logging.error(f"Failed to create volume control '{control_name}'")
            return None


def main():
    # Configure logging FIRST, before any other operations
    import sys
    parser = argparse.ArgumentParser(description="Detect and display sound card details.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (INFO level).",
    )
    parser.add_argument(
        "-vv",
        "--very-verbose",
        action="store_true",
        help="Enable very verbose logging (DEBUG level).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available HiFiBerry sound cards with their device tree overlays.",
    )
    parser.add_argument(
        "--list-format",
        choices=["table", "csv"],
        default="table",
        help="Output format for --list option (default: table).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format.",
    )
    parser.add_argument(
        "--name",
        action="store_true",
        help="Print only the name of the detected sound card.",
    )
    parser.add_argument(
        "--volume-control",
        action="store_true",
        help="Print only the volume control of the detected sound card.",
    )
    parser.add_argument(
        "--volume-control-softvol",
        action="store_true",
        help="Print the volume control of the detected sound card, falling back to 'Softvol' if none defined.",
    )
    parser.add_argument(
        "--headphone-volume-control",
        action="store_true",
        help="Print only the headphone volume control of the detected sound card.",
    )
    parser.add_argument(
        "--hw",
        action="store_true",
        help="Print only the hardware index of the detected sound card.",
    )
    parser.add_argument(
        "--output-channels",
        action="store_true",
        help="Print only the number of output channels.",
    )
    parser.add_argument(
        "--input-channels",
        action="store_true",
        help="Print only the number of input channels.",
    )
    parser.add_argument(
        "--features",
        action="store_true",
        help="Print only the features of the detected sound card.",
    )
    parser.add_argument(
        "--no-eeprom",
        action="store_true",
        help="Disable EEPROM check and use only aplay -l for detection.",
    )
    parser.add_argument(
        "--create-volume-control",
        metavar="CONTROL_NAME",
        help="Create a dummy ALSA volume control with the specified name.",
    )
    parser.add_argument(
        "--get-or-create-volume-control",
        metavar="CONTROL_NAME",
        help="Get existing volume control or create a dummy one with the specified name (defaults to 'Softvol').",
    )
    parser.add_argument(
        "--detected",
        action="store_true",
        help="Print the name of the detected sound card if one is found, nothing otherwise. Exit code 1 if no card detected.",
    )
    
    if ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)
    
    args = parser.parse_args()

    # Configure logging immediately after parsing args
    # Remove any existing handlers and configure from scratch
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    if args.very_verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr, force=True)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
    else:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr, force=True)
        # Also set the root logger level explicitly
        logging.getLogger().setLevel(logging.ERROR)

    # Handle list functionality first (no need for sound card detection)
    if args.list:
        list_all_sound_cards(args.list_format)
        return

    # Handle --detected option (check if sound card is detected)
    if args.detected:
        card = Soundcard(no_eeprom=args.no_eeprom)
        if card.name != UNKNOWN_CARD_NAME:
            print(card.name)
            sys.exit(0)
        else:
            # No sound card detected, exit with code 1
            sys.exit(1)

    # Handle dummy control creation (requires sound card detection)
    if args.create_volume_control:
        card = Soundcard(no_eeprom=args.no_eeprom)
        if card.create_dummy_alsa_control(args.create_volume_control):
            print(f"Successfully created volume control: {args.create_volume_control}")
        else:
            print(f"Failed to create volume control: {args.create_volume_control}")
            sys.exit(1)
        return

    if args.get_or_create_volume_control:
        card = Soundcard(no_eeprom=args.no_eeprom)
        control_name = card.get_or_create_volume_control(args.get_or_create_volume_control)
        if control_name:
            print(control_name)
        else:
            print("Failed to get or create volume control")
            sys.exit(1)
        return

    card = Soundcard(no_eeprom=args.no_eeprom)

    # Check if any specific output option is selected
    specific_output = any([
        args.name, 
        args.volume_control,
        args.volume_control_softvol,
        args.headphone_volume_control,
        args.hw,
        args.output_channels, 
        args.input_channels, 
        args.features,
        args.json,
        args.create_volume_control,
        args.get_or_create_volume_control,
        args.detected
    ])

    if args.json:
        import json
        card_data = {
            "name": card.name,
            "volume_control": card.volume_control,
            "headphone_volume_control": card.headphone_volume_control,
            "hardware_index": card.get_hardware_index(),
            "output_channels": card.output_channels,
            "input_channels": card.input_channels,
            "features": card.features,
            "hat_name": card.hat_name,
            "supports_dsp": card.supports_dsp,
            "card_type": card.card_type
        }
        print(json.dumps(card_data, indent=2))
    elif args.name:
        print(card.name)
    elif args.volume_control:
        print(card.volume_control if card.volume_control else "")
    elif args.volume_control_softvol:
        print(card.get_mixer_control_name(use_softvol_fallback=True))
    elif args.headphone_volume_control:
        print(card.get_headphone_volume_control_name() if card.get_headphone_volume_control_name() else "")
    elif args.hw:
        hw_index = card.get_hardware_index()
        print(hw_index if hw_index is not None else "")
    elif args.output_channels:
        print(card.output_channels)
    elif args.input_channels:
        print(card.input_channels)
    elif args.features:
        print(','.join(card.features) if card.features else "")
    else:
        # Default output format when no specific option is selected
        print("Sound card details:")
        print(f"Name: {card.name}")
        print(f"Volume Control: {card.volume_control}")
        print(f"Headphone Volume Control: {card.headphone_volume_control or 'None'}")
        print(f"Hardware Index: {card.get_hardware_index()}")
        print(f"Output Channels: {card.output_channels}")
        print(f"Input Channels: {card.input_channels}")
        print(f"Features: {', '.join(card.features) if card.features else 'None'}")
        print(f"HAT Name: {card.hat_name or 'None'}")
        print(f"Supports DSP: {'Yes' if card.supports_dsp else 'No'}")
        print(f"Card Type: {', '.join(card.card_type) if card.card_type else 'None'}")


if __name__ == "__main__":
    main()

