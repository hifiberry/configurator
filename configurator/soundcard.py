import subprocess
import logging
import argparse

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
    },
    "DAC8x": {
        "aplay_contains": "DAC8x",
        "hat_name": "DAC8x",
        "volume_control": None,
        "output_channels": 8,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
    },
    "Digi2 Pro": {
        "hat_name": "Digi2 Pro",
        "volume_control": "Softvol",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp"],
        "supports_dsp": True,
    },
    "Amp100": {
        "hat_name": "Amp100",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["spdifnoclock", "toslink"],
        "supports_dsp": False,
    },
    "Amp3": {
        "aplay_contains": "Amp3",
        "hat_name": "Amp3",
        "volume_control": "A.Mstr Vol",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": False,
    },
    "Amp4": {
        "hat_name": "Amp4",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": True,
    },
    "Amp4 Pro": {
        "aplay_contains": "Amp4 Pro",
        "hat_name": "Amp4 Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["usehwvolume"],
        "supports_dsp": True,
    },
    "DSP 2x4": {
        "aplay_contains": "DSP 2x4",
        "hat_name": "DSP 2x4",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp"],
        "supports_dsp": False,
    },
    "DAC+ ADC Pro": {
        "aplay_contains": "DAC+ADC Pro",
        "hat_name": "DAC+ ADC Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": False,
    },
    "DAC+ ADC": {
        "aplay_contains": "DAC+ ADC",
        "hat_name": "DAC+ ADC",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": False,
    },
    "DAC2 ADC Pro": {
        "aplay_contains": "DAC2 ADC Pro",
        "hat_name": "DAC2 ADC Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 2,
        "features": ["analoginput"],
        "supports_dsp": True,
    },
    "DAC2 HD": {
        "aplay_contains": "DAC2 HD",
        "hat_name": "DAC2 HD",
        "volume_control": "DAC",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": True,
    },
    "DAC+ DSP": {
        "aplay_contains": "DAC+DSP",
        "hat_name": "DAC+ DSP",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["toslink"],
        "supports_dsp": False,
    },
    "DAC+/Amp2": {
        "aplay_contains": "DAC+",
        "hat_name": None,
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
    },
    "DAC2 Pro": {
        "hat_name": "DAC2 Pro",
        "volume_control": "Digital",
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
    },
    "Amp+": {
        "aplay_contains": "AMP",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
    },
    "Digi+ Pro": {
        "aplay_contains": "Digi Pro",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["digi"],
        "supports_dsp": True,
    },
    "Digi+": {
        "aplay_contains": "Digi",
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["digi"],
        "supports_dsp": False,
    },
    "Beocreate 4-Channel Amplifier": {
        "aplay_contains": None,
        "hat_name": "Beocreate 4-Channel Amplifier",
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp", "toslink"],
        "supports_dsp": False,
    },
    "DAC+ Zero/Light/MiniAmp": {
        "aplay_contains": None,
        "hat_name": None,
        "volume_control": None,
        "output_channels": 2,
        "input_channels": 0,
        "features": [],
        "supports_dsp": False,
    },
}


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
    ):
        if name is None:
            detected_card = self._detect_card()
            if detected_card:
                self.name = detected_card["name"]
                self.volume_control = detected_card.get("volume_control")
                self.output_channels = detected_card.get("output_channels", 2)
                self.input_channels = detected_card.get("input_channels", 0)
                self.features = detected_card.get("features", [])
                self.hat_name = detected_card.get("hat_name")
                self.supports_dsp = detected_card.get("supports_dsp", False)
            else:
                self.name = "Unknown"
                self.volume_control = volume_control
                self.output_channels = output_channels
                self.input_channels = input_channels
                self.features = features or []
                self.hat_name = hat_name
                self.supports_dsp = supports_dsp
        else:
            self.name = name
            self.volume_control = volume_control
            self.output_channels = output_channels
            self.input_channels = input_channels
            self.features = features or []
            self.hat_name = hat_name
            self.supports_dsp = supports_dsp

    def __str__(self):
        return (
            f"Soundcard(name={self.name}, volume_control={self.volume_control}, "
            f"output_channels={self.output_channels}, input_channels={self.input_channels}, "
            f"features={self.features}, hat_name={self.hat_name}, supports_dsp={self.supports_dsp})"
        )

    def _detect_card(self):
        try:
            # Use get_hat_info function to get HAT information
            try:
                hat_info = get_hat_info()
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

            output = subprocess.check_output("aplay -l", shell=True, text=True).strip()
            if "hifiberry" not in output.lower():
                logging.warning("No HiFiBerry sound card detected.")
                return None

            for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                aplay_contains = attributes.get("aplay_contains", "").lower()
                if aplay_contains and aplay_contains in output.lower():
                    return {"name": card_name, **attributes}
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
    args = parser.parse_args()

    if args.very_verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    card = Soundcard()

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
            "supports_dsp": card.supports_dsp
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


if __name__ == "__main__":
    main()

