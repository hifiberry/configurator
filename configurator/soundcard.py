import subprocess
import logging
import argparse
import sys

# Import the get_hat_info function from hattools
from configurator.hattools import get_hat_info

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
        "volume_control": "Softvol",
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
    "DSP 2x4": {
        "aplay_contains": "DSP 2x4",
        "hat_name": "DSP 2x4",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp"],
        "supports_dsp": False,
        "card_type": ["DAC", "ADC", "Digi"],
        "dtoverlay": "hifiberry-dacplusdsp",
        "is_pro": False,
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
        "aplay_contains": "DAC2 HD",
        "hat_name": "DAC2 HD",
        "volume_control": "DAC",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": True,
        "card_type": ["DAC"],
        "dtoverlay": "hifiberry-dacplushd",
        "is_pro": True,
    },
    "DAC+ DSP": {
        "aplay_contains": "DAC+DSP",
        "hat_name": "DAC+ DSP",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["toslink"],
        "supports_dsp": False,
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
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
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
        "volume_control": None,
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
        "volume_control": "Softvol",
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
        "volume_control": "Softvol",
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
        "volume_control": "Softvol",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
        "card_type": ["Amp"],
        "dtoverlay": "hifiberry-dac",
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
        output_channels=2,
        input_channels=0,
        features=None,
        hat_name=None,
        supports_dsp=False,
        card_type=None,
        no_eeprom=False,
    ):
        if name is None:
            detected_card = self._detect_card(no_eeprom=no_eeprom)
            if detected_card:
                self.name = detected_card["name"]
                self.volume_control = detected_card.get("volume_control")
                self.output_channels = detected_card.get("output_channels", 2)
                self.input_channels = detected_card.get("input_channels", 0)
                self.features = detected_card.get("features", [])
                self.hat_name = detected_card.get("hat_name")
                self.supports_dsp = detected_card.get("supports_dsp", False)
                self.card_type = detected_card.get("card_type", [])
            else:
                self.name = "Unknown"
                self.volume_control = volume_control
                self.output_channels = output_channels
                self.input_channels = input_channels
                self.features = features or []
                self.hat_name = hat_name
                self.supports_dsp = supports_dsp
                self.card_type = card_type or []
        else:
            self.name = name
            self.volume_control = volume_control
            self.output_channels = output_channels
            self.input_channels = input_channels
            self.features = features or []
            self.hat_name = hat_name
            self.supports_dsp = supports_dsp
            self.card_type = card_type or []

    def __str__(self):
        return (
            f"Soundcard(name={self.name}, volume_control={self.volume_control}, "
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
        try:
            # Use get_hat_info function to get HAT information (unless disabled)
            if not no_eeprom:
                try:
                    hat_info = get_hat_info(verbose=False)
                    vendor = hat_info.get("vendor")
                    product = hat_info.get("product")
                    
                    if product:
                        potential_matches = [
                            (card_name, attributes)
                            for card_name, attributes in SOUND_CARD_DEFINITIONS.items()
                            if attributes.get("hat_name") == product
                        ]
                        if len(potential_matches) == 1:
                            return {"name": potential_matches[0][0], **potential_matches[0][1]}
                        elif len(potential_matches) > 1:
                            logging.info(f"Multiple matches for HAT {product}. Using `aplay -l` to distinguish.")
                        else:
                            logging.warning(f"No matching HAT found for {product}. Falling back to `aplay -l`.")
                    else:
                        logging.warning("No product information found in HAT. Falling back to `aplay -l`.")
                except Exception as e:
                    logging.warning(f"HAT detection failed: {str(e)}")
            else:
                logging.info("EEPROM check disabled, using aplay -l for detection")

            output = subprocess.check_output("aplay -l", shell=True, text=True).strip()
            if "hifiberry" not in output.lower():
                logging.warning("No HiFiBerry sound card detected.")
                return None

            # First pass: try to match based on aplay_contains patterns
            initial_detection = None
            for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                aplay_contains = attributes.get("aplay_contains", "")
                if aplay_contains and aplay_contains.lower() in output.lower():
                    initial_detection = {"name": card_name, **attributes}
                    break
            
            # Second pass: perform additional checks to refine detection
            final_detection = self._additional_card_checks(output, initial_detection)
            if final_detection:
                return final_detection
        except subprocess.CalledProcessError:
            logging.error("Error: Unable to execute `aplay -l`. Ensure ALSA is installed and configured.")

        logging.warning("No matching sound card detected.")
        return None

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

    card = Soundcard(no_eeprom=args.no_eeprom)

    # Check if any specific output option is selected
    specific_output = any([
        args.name, 
        args.volume_control,
        args.volume_control_softvol,
        args.hw,
        args.output_channels, 
        args.input_channels, 
        args.features,
        args.json
    ])

    if args.json:
        import json
        card_data = {
            "name": card.name,
            "volume_control": card.volume_control,
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
        print(f"Hardware Index: {card.get_hardware_index()}")
        print(f"Output Channels: {card.output_channels}")
        print(f"Input Channels: {card.input_channels}")
        print(f"Features: {', '.join(card.features) if card.features else 'None'}")
        print(f"HAT Name: {card.hat_name or 'None'}")
        print(f"Supports DSP: {'Yes' if card.supports_dsp else 'No'}")
        print(f"Card Type: {', '.join(card.card_type) if card.card_type else 'None'}")


if __name__ == "__main__":
    main()

