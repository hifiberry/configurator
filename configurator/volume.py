#!/usr/bin/env python3
"""
HiFiBerry Volume Storage Utility

Store and restore ALSA volume settings in the configuration database
"""

import sys
import os
import logging
import argparse
import subprocess

from configurator.configdb import ConfigDB
from configurator.soundcard import Soundcard

# Configuration keys for volume storage
VOLUME_DB_KEY = "system.volume"
VOLUME_CARD_DB_KEY = "system.volume.card"
VOLUME_CONTROL_DB_KEY = "system.volume.control"

def get_current_volume(card_index, control_name):
    """
    Get the current volume setting from ALSA
    
    Args:
        card_index: ALSA card index
        control_name: Name of the volume control
    
    Returns:
        Volume value as string, or None if retrieval fails
    """
    if card_index is None or control_name is None:
        logging.error("Cannot get volume: card_index or control_name is None")
        return None
        
    try:
        cmd = f"amixer -c {card_index} get '{control_name}'"
        output = subprocess.check_output(cmd, shell=True, text=True)
        
        # Look for percentage in the output, e.g. [80%]
        import re
        matches = re.search(r'\[(\d+)%\]', output)
        if matches:
            return matches.group(1)
        
        # If no percentage is found, look for dB value
        matches = re.search(r'\[(-?\d+\.\d+)dB\]', output)
        if matches:
            return matches.group(1)
            
        logging.warning(f"Could not parse volume from output: {output}")
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting volume: {str(e)}")
        return None

def set_volume(card_index, control_name, volume_value):
    """
    Set the volume using ALSA
    
    Args:
        card_index: ALSA card index
        control_name: Name of the volume control
        volume_value: Volume value to set (percentage or dB)
    
    Returns:
        True if successful, False otherwise
    """
    if card_index is None or control_name is None:
        logging.error("Cannot set volume: card_index or control_name is None")
        return False
        
    try:
        # Check if the value is numeric (dB) or should be treated as percentage
        try:
            float_value = float(volume_value)
            # If it's a float that's not a whole number, treat as dB
            if float_value != int(float_value):
                cmd = f"amixer -c {card_index} set '{control_name}' {volume_value}dB"
            else:
                cmd = f"amixer -c {card_index} set '{control_name}' {volume_value}%"
        except ValueError:
            # If conversion fails, just pass the value as-is
            cmd = f"amixer -c {card_index} set '{control_name}' {volume_value}"
            
        subprocess.check_output(cmd, shell=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error setting volume: {str(e)}")
        return False

def store_volume():
    """
    Store the current volume setting in the configuration database
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get sound card information
        card = Soundcard()
        card_index = card.get_hardware_index()
        control_name = card.get_mixer_control_name(use_softvol_fallback=True)
        
        if card_index is None:
            logging.error("No HiFiBerry sound card detected")
            return False
            
        if control_name is None:
            logging.error("No volume control available for this sound card")
            return False
            
        # Get current volume
        volume = get_current_volume(card_index, control_name)
        if volume is None:
            logging.error("Could not retrieve current volume")
            return False
            
        # Store in database
        db = ConfigDB()
        db.set(VOLUME_DB_KEY, volume)
        db.set(VOLUME_CARD_DB_KEY, str(card_index))
        db.set(VOLUME_CONTROL_DB_KEY, control_name)
        
        logging.info(f"Volume {volume} stored for card {card_index}, control '{control_name}'")
        return True
    except Exception as e:
        logging.error(f"Error storing volume: {str(e)}")
        return False

def restore_volume():
    """
    Restore volume from the configuration database
    
    Returns:
        True if successful, False otherwise
    """
    try:
        db = ConfigDB()
        
        # Get stored values
        volume = db.get(VOLUME_DB_KEY)
        stored_card_index = db.get(VOLUME_CARD_DB_KEY)
        stored_control_name = db.get(VOLUME_CONTROL_DB_KEY)
        
        if volume is None:
            logging.warning("No volume setting found in configuration database")
            return False
            
        # Get current sound card information
        card = Soundcard()
        card_index = card.get_hardware_index()
        control_name = card.get_mixer_control_name(use_softvol_fallback=True)
        
        if card_index is None:
            logging.error("No HiFiBerry sound card detected")
            return False
            
        if control_name is None:
            logging.error("No volume control available for this sound card")
            return False
            
        # Check if the sound card has changed
        if stored_card_index != str(card_index) or stored_control_name != control_name:
            logging.warning(f"Sound card configuration has changed from card {stored_card_index}, "
                           f"control '{stored_control_name}' to card {card_index}, control '{control_name}'")
        
        # Set the volume
        result = set_volume(card_index, control_name, volume)
        if result:
            logging.info(f"Volume restored to {volume} for card {card_index}, control '{control_name}'")
            return True
        else:
            logging.error("Failed to restore volume")
            return False
    except Exception as e:
        logging.error(f"Error restoring volume: {str(e)}")
        return False

def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s: %(message)s')

    # Create the parser
    parser = argparse.ArgumentParser(
        description='Store and restore ALSA volume settings in the configuration database')
    
    # Add store/restore group
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--store', action='store_true', help='Store the current volume setting')
    group.add_argument('--restore', action='store_true', help='Restore the stored volume setting')
    
    # Add verbosity option
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Execute command
    if args.store:
        result = store_volume()
    elif args.restore:
        result = restore_volume()
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())