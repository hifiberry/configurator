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

try:
    import alsaaudio
    ALSA_AVAILABLE = True
except ImportError:
    ALSA_AVAILABLE = False
    logging.warning("alsaaudio module not available, falling back to subprocess calls")

from configurator.configdb import ConfigDB
from configurator.soundcard import Soundcard

# Configuration keys for volume storage
VOLUME_DB_KEY = "system.volume"
VOLUME_CARD_DB_KEY = "system.volume.card"
VOLUME_CONTROL_DB_KEY = "system.volume.control"

# Headphone volume configuration keys
HEADPHONE_VOLUME_DB_KEY = "system.volume.headphone"
HEADPHONE_VOLUME_CARD_DB_KEY = "system.volume.headphone.card"
HEADPHONE_VOLUME_CONTROL_DB_KEY = "system.volume.headphone.control"

# PipeWire virtual device configuration keys
PIPEWIRE_MASTER_VOLUME_KEY = "system.volume.pipewire.master"
PIPEWIRE_CAPTURE_VOLUME_KEY = "system.volume.pipewire.capture"

# List of known headphone volume control names
HEADPHONE_VOLUME_CONTROLS = ["Headphone"]

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
    
    if ALSA_AVAILABLE:
        try:
            # Use alsaaudio library for direct access
            mixer = alsaaudio.Mixer(control_name, cardindex=card_index)
            volume = mixer.getvolume()
            if volume:
                # Return the first channel's volume (usually both channels are the same)
                return str(volume[0])
            else:
                logging.warning(f"No volume data returned for control '{control_name}' on card {card_index}")
                return None
        except alsaaudio.ALSAAudioError as e:
            logging.error(f"ALSA error getting volume: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error getting volume via ALSA API: {str(e)}")
            return None
    else:
        # Fallback to subprocess
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
    
    if ALSA_AVAILABLE:
        try:
            # Use alsaaudio library for direct access
            mixer = alsaaudio.Mixer(control_name, cardindex=card_index)
            
            # Convert volume_value to integer if it's a percentage
            try:
                volume_int = int(float(volume_value))
                # Ensure volume is within valid range (0-100)
                volume_int = max(0, min(100, volume_int))
                mixer.setvolume(volume_int)
                return True
            except ValueError:
                logging.error(f"Invalid volume value: {volume_value}")
                return False
        except alsaaudio.ALSAAudioError as e:
            logging.error(f"ALSA error setting volume: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Error setting volume via ALSA API: {str(e)}")
            return False
    else:
        # Fallback to subprocess
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
    success = True
    
    try:
        # Store physical card volume if available
        card = Soundcard()
        card_index = card.get_hardware_index()
        control_name = card.get_mixer_control_name(use_softvol_fallback=True)
        
        if card_index is not None and control_name is not None:
            # Get current volume from physical card
            volume = get_current_volume(card_index, control_name)
            if volume is not None:
                # Store in database
                db = ConfigDB()
                db.set(VOLUME_DB_KEY, volume)
                db.set(VOLUME_CARD_DB_KEY, str(card_index))
                db.set(VOLUME_CONTROL_DB_KEY, control_name)
                
                logging.info(f"Physical card volume {volume} stored for card {card_index}, control '{control_name}'")
            else:
                logging.warning("Could not retrieve current volume from physical card")
                success = False
        else:
            logging.warning("No HiFiBerry sound card detected or no volume control available")
            success = False
        
        # Store headphone volume if available
        headphone_result = store_headphone_volume()
        if not headphone_result:
            logging.info("No headphone volume controls available or failed to store")
        
        # Store PipeWire virtual controls if available
        if is_pipewire_available():
            db = ConfigDB()
            
            # Store Master volume
            master_volume = get_pipewire_volume('Master')
            if master_volume is not None:
                db.set(PIPEWIRE_MASTER_VOLUME_KEY, master_volume)
                logging.info(f"PipeWire Master volume {master_volume} stored")
            else:
                logging.warning("Could not retrieve PipeWire Master volume")
            
            # Store Capture volume
            capture_volume = get_pipewire_volume('Capture')
            if capture_volume is not None:
                db.set(PIPEWIRE_CAPTURE_VOLUME_KEY, capture_volume)
                logging.info(f"PipeWire Capture volume {capture_volume} stored")
            else:
                logging.warning("Could not retrieve PipeWire Capture volume")
        else:
            logging.info("PipeWire virtual controls not available")
            
        return success
    except Exception as e:
        logging.error(f"Error storing volume: {str(e)}")
        return False

def restore_volume():
    """
    Restore volume from the configuration database
    
    Returns:
        True if successful, False otherwise
    """
    success = True
    
    try:
        db = ConfigDB()
        
        # Restore physical card volume if available
        volume = db.get(VOLUME_DB_KEY)
        stored_card_index = db.get(VOLUME_CARD_DB_KEY)
        stored_control_name = db.get(VOLUME_CONTROL_DB_KEY)
        
        if volume is not None and stored_card_index is not None and stored_control_name is not None:
            # Get current sound card information
            card = Soundcard()
            card_index = card.get_hardware_index()
            control_name = card.get_mixer_control_name(use_softvol_fallback=True)
            
            if card_index is not None and control_name is not None:
                # Check if the sound card has changed
                if stored_card_index != str(card_index) or stored_control_name != control_name:
                    logging.warning(f"Sound card configuration has changed from card {stored_card_index}, "
                                   f"control '{stored_control_name}' to card {card_index}, control '{control_name}'")
                
                # Set the volume
                result = set_volume(card_index, control_name, volume)
                if result:
                    logging.info(f"Physical card volume restored to {volume} for card {card_index}, control '{control_name}'")
                else:
                    logging.error("Failed to restore physical card volume")
                    success = False
            else:
                logging.warning("No HiFiBerry sound card detected for volume restoration")
                success = False
        else:
            logging.warning("No physical card volume setting found in configuration database")
            success = False
        
        # Restore headphone volume if available
        headphone_result = restore_headphone_volume()
        if not headphone_result:
            logging.info("No headphone volume settings found or failed to restore")
        
        # Restore PipeWire virtual controls if available
        if is_pipewire_available():
            # Restore Master volume
            master_volume = db.get(PIPEWIRE_MASTER_VOLUME_KEY)
            if master_volume is not None:
                result = set_pipewire_volume('Master', master_volume)
                if result:
                    logging.info(f"PipeWire Master volume restored to {master_volume}")
                else:
                    logging.error("Failed to restore PipeWire Master volume")
            else:
                logging.warning("No PipeWire Master volume setting found in configuration database")
            
            # Restore Capture volume
            capture_volume = db.get(PIPEWIRE_CAPTURE_VOLUME_KEY)
            if capture_volume is not None:
                result = set_pipewire_volume('Capture', capture_volume)
                if result:
                    logging.info(f"PipeWire Capture volume restored to {capture_volume}")
                else:
                    logging.error("Failed to restore PipeWire Capture volume")
            else:
                logging.warning("No PipeWire Capture volume setting found in configuration database")
        else:
            logging.info("PipeWire virtual controls not available for restoration")
            
        return success
    except Exception as e:
        logging.error(f"Error restoring volume: {str(e)}")
        return False

def is_pipewire_available():
    """
    Check if PipeWire virtual controls are available
    
    Returns:
        True if PipeWire Master control is available, False otherwise
    """
    if ALSA_AVAILABLE:
        try:
            # Try to access Master control using ALSA API
            mixer = alsaaudio.Mixer('Master')
            return True
        except alsaaudio.ALSAAudioError:
            return False
        except Exception:
            return False
    else:
        # Fallback to subprocess
        try:
            cmd = "amixer get Master"
            output = subprocess.check_output(cmd, shell=True, text=True)
            return "Simple mixer control 'Master'" in output
        except subprocess.CalledProcessError:
            return False

def get_pipewire_volume(control_name):
    """
    Get the current volume setting from PipeWire virtual controls
    
    Args:
        control_name: Name of the control ('Master' or 'Capture')
    
    Returns:
        Volume value as string, or None if retrieval fails
    """
    if ALSA_AVAILABLE:
        try:
            # Use alsaaudio library for direct access
            if control_name == 'Capture':
                mixer = alsaaudio.Mixer(control_name, id=0, cardindex=-1)
            else:
                mixer = alsaaudio.Mixer(control_name, cardindex=-1)
            volume = mixer.getvolume()
            if volume:
                # Return the first channel's volume (usually both channels are the same)
                return str(volume[0])
            else:
                logging.warning(f"No volume data returned for PipeWire control '{control_name}'")
                return None
        except alsaaudio.ALSAAudioError as e:
            logging.error(f"ALSA error getting PipeWire volume: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error getting PipeWire volume via ALSA API: {str(e)}")
            return None
    else:
        # Fallback to subprocess
        try:
            cmd = f"amixer get '{control_name}'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            
            # Look for percentage in the output, e.g. [80%]
            import re
            matches = re.search(r'\[(\d+)%\]', output)
            if matches:
                return matches.group(1)
                
            logging.warning(f"Could not parse volume from PipeWire output: {output}")
            return None
        except subprocess.CalledProcessError as e:
            logging.error(f"Error getting PipeWire volume: {str(e)}")
            return None

def set_pipewire_volume(control_name, volume_value):
    """
    Set the volume using PipeWire virtual controls
    
    Args:
        control_name: Name of the control ('Master' or 'Capture')
        volume_value: Volume value to set (percentage)
    
    Returns:
        True if successful, False otherwise
    """
    if ALSA_AVAILABLE:
        try:
            # Use alsaaudio library for direct access
            if control_name == 'Capture':
                mixer = alsaaudio.Mixer(control_name, id=0, cardindex=-1)
            else:
                mixer = alsaaudio.Mixer(control_name, cardindex=-1)
            
            # Convert volume_value to integer
            try:
                volume_int = int(float(volume_value))
                # Ensure volume is within valid range (0-100)
                volume_int = max(0, min(100, volume_int))
                mixer.setvolume(volume_int)
                return True
            except ValueError:
                logging.error(f"Invalid PipeWire volume value: {volume_value}")
                return False
        except alsaaudio.ALSAAudioError as e:
            logging.error(f"ALSA error setting PipeWire volume: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Error setting PipeWire volume via ALSA API: {str(e)}")
            return False
    else:
        # Fallback to subprocess
        try:
            cmd = f"amixer set '{control_name}' {volume_value}%"
            subprocess.check_output(cmd, shell=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Error setting PipeWire volume: {str(e)}")
            return False

def get_available_headphone_controls():
    """
    Get list of available headphone volume controls on the current sound card
    
    Returns:
        List of available headphone control names, empty if none found
    """
    try:
        card = Soundcard()
        card_index = card.get_hardware_index()
        
        if card_index is None:
            logging.error("No sound card detected")
            return []
        
        # Get all available controls on the sound card
        available_controls = list_available_controls(card_index)
        
        # Filter for headphone controls
        headphone_controls = []
        for control in HEADPHONE_VOLUME_CONTROLS:
            if control in available_controls:
                headphone_controls.append(control)
        
        return headphone_controls
    except Exception as e:
        logging.error(f"Error getting available headphone controls: {str(e)}")
        return []

def get_headphone_volume():
    """
    Get the current headphone volume setting
    
    Returns:
        Tuple of (volume_value, control_name) if successful, (None, None) if failed
    """
    try:
        card = Soundcard()
        card_index = card.get_hardware_index()
        
        if card_index is None:
            logging.error("No sound card detected")
            return None, None
        
        # Get available headphone controls
        headphone_controls = get_available_headphone_controls()
        
        if not headphone_controls:
            logging.error("No headphone volume controls available on this sound card")
            return None, None
        
        # Use the first available headphone control
        control_name = headphone_controls[0]
        volume = get_current_volume(card_index, control_name)
        
        if volume is not None:
            return volume, control_name
        else:
            logging.error(f"Failed to get volume for headphone control '{control_name}'")
            return None, None
            
    except Exception as e:
        logging.error(f"Error getting headphone volume: {str(e)}")
        return None, None

def set_headphone_volume(volume_value):
    """
    Set the headphone volume
    
    Args:
        volume_value: Volume value to set (percentage or dB)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        card = Soundcard()
        card_index = card.get_hardware_index()
        
        if card_index is None:
            logging.error("No sound card detected")
            return False
        
        # Get available headphone controls
        headphone_controls = get_available_headphone_controls()
        
        if not headphone_controls:
            logging.error("No headphone volume controls available on this sound card")
            return False
        
        # Use the first available headphone control
        control_name = headphone_controls[0]
        result = set_volume(card_index, control_name, volume_value)
        
        if result:
            logging.info(f"Headphone volume set to {volume_value} for control '{control_name}'")
            return True
        else:
            logging.error(f"Failed to set headphone volume for control '{control_name}'")
            return False
            
    except Exception as e:
        logging.error(f"Error setting headphone volume: {str(e)}")
        return False

def store_headphone_volume():
    """
    Store the current headphone volume setting in the configuration database
    
    Returns:
        True if successful, False otherwise
    """
    try:
        card = Soundcard()
        card_index = card.get_hardware_index()
        
        if card_index is None:
            logging.error("No sound card detected")
            return False
        
        # Get available headphone controls
        headphone_controls = get_available_headphone_controls()
        
        if not headphone_controls:
            logging.error("No headphone volume controls available on this sound card")
            return False
        
        # Use the first available headphone control
        control_name = headphone_controls[0]
        volume = get_current_volume(card_index, control_name)
        
        if volume is not None:
            # Store in database
            db = ConfigDB()
            db.set(HEADPHONE_VOLUME_DB_KEY, volume)
            db.set(HEADPHONE_VOLUME_CARD_DB_KEY, str(card_index))
            db.set(HEADPHONE_VOLUME_CONTROL_DB_KEY, control_name)
            
            logging.info(f"Headphone volume {volume} stored for card {card_index}, control '{control_name}'")
            return True
        else:
            logging.error("Could not retrieve current headphone volume")
            return False
            
    except Exception as e:
        logging.error(f"Error storing headphone volume: {str(e)}")
        return False

def restore_headphone_volume():
    """
    Restore headphone volume from the configuration database
    
    Returns:
        True if successful, False otherwise
    """
    try:
        db = ConfigDB()
        
        # Get stored headphone volume settings
        volume = db.get(HEADPHONE_VOLUME_DB_KEY)
        stored_card_index = db.get(HEADPHONE_VOLUME_CARD_DB_KEY)
        stored_control_name = db.get(HEADPHONE_VOLUME_CONTROL_DB_KEY)
        
        if volume is None:
            logging.warning("No headphone volume setting found in configuration database")
            return False
        
        # Get current sound card information
        card = Soundcard()
        card_index = card.get_hardware_index()
        
        if card_index is None:
            logging.error("No sound card detected for headphone volume restoration")
            return False
        
        # Get available headphone controls
        headphone_controls = get_available_headphone_controls()
        
        if not headphone_controls:
            logging.error("No headphone volume controls available on current sound card")
            return False
        
        # Use the first available headphone control
        control_name = headphone_controls[0]
        
        # Check if the sound card or control has changed
        if stored_card_index and stored_control_name:
            if stored_card_index != str(card_index) or stored_control_name != control_name:
                logging.warning(f"Headphone configuration has changed from card {stored_card_index}, "
                               f"control '{stored_control_name}' to card {card_index}, control '{control_name}'")
        
        # Set the headphone volume
        result = set_volume(card_index, control_name, volume)
        
        if result:
            logging.info(f"Headphone volume restored to {volume} for card {card_index}, control '{control_name}'")
            return True
        else:
            logging.error("Failed to restore headphone volume")
            return False
            
    except Exception as e:
        logging.error(f"Error restoring headphone volume: {str(e)}")
        return False

def list_available_controls(card_index=None):
    """
    List available ALSA mixer controls for debugging
    
    Args:
        card_index: ALSA card index (None for default card)
    
    Returns:
        List of control names or empty list if error
    """
    controls = []
    
    if ALSA_AVAILABLE:
        try:
            if card_index is not None:
                mixer_list = alsaaudio.mixers(cardindex=card_index)
            else:
                mixer_list = alsaaudio.mixers()
            controls = list(mixer_list)
            logging.debug(f"Available ALSA controls: {controls}")
        except Exception as e:
            logging.error(f"Error listing ALSA controls: {str(e)}")
    else:
        try:
            if card_index is not None:
                cmd = f"amixer -c {card_index} scontrols"
            else:
                cmd = "amixer scontrols"
            output = subprocess.check_output(cmd, shell=True, text=True)
            
            import re
            matches = re.findall(r"Simple mixer control '([^']+)'", output)
            controls = matches
            logging.debug(f"Available ALSA controls: {controls}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error listing ALSA controls: {str(e)}")
    
    return controls

def main():
    # Configure logging to send messages to stderr
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s: %(message)s',
                        stream=sys.stderr)

    # Create the parser
    parser = argparse.ArgumentParser(
        description='Store and restore ALSA volume settings (including PipeWire virtual controls and headphone volume) in the configuration database')
    
    # Add store/restore group
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--store', action='store_true', 
                      help='Store the current volume settings (both physical card, headphone, and PipeWire virtual controls)')
    group.add_argument('--restore', action='store_true', 
                      help='Restore the stored volume settings (both physical card, headphone, and PipeWire virtual controls)')
    
    # Add headphone volume specific options
    group.add_argument('--store-headphone', action='store_true',
                      help='Store only the current headphone volume setting')
    group.add_argument('--restore-headphone', action='store_true',
                      help='Restore only the stored headphone volume setting')
    group.add_argument('--get-headphone', action='store_true',
                      help='Get the current headphone volume')
    group.add_argument('--set-headphone', type=str, metavar='VOLUME',
                      help='Set the headphone volume (percentage or dB value)')
    group.add_argument('--list-headphone', action='store_true',
                      help='List available headphone volume controls')
    
    # Add verbosity option
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    
    # Add debug option to list available controls
    parser.add_argument('--list-controls', action='store_true', help='List available ALSA mixer controls and exit')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Log ALSA API availability
    if args.verbose:
        if ALSA_AVAILABLE:
            logging.info("Using Python ALSA API (alsaaudio)")
        else:
            logging.info("Using subprocess calls to amixer (alsaaudio not available)")
    
    # Handle list controls option
    if args.list_controls:
        print("Available ALSA mixer controls:")
        
        # List physical card controls
        card = Soundcard()
        card_index = card.get_hardware_index()
        if card_index is not None:
            print(f"\nPhysical card {card_index} controls:")
            controls = list_available_controls(card_index)
            for control in controls:
                print(f"  - {control}")
        
        # List default/PipeWire controls
        print(f"\nDefault card controls:")
        controls = list_available_controls()
        for control in controls:
            print(f"  - {control}")
        
        return 0
    
    # Handle headphone-specific operations
    if args.list_headphone:
        headphone_controls = get_available_headphone_controls()
        if headphone_controls:
            print("Available headphone volume controls:")
            for control in headphone_controls:
                print(f"  - {control}")
        else:
            print("No headphone volume controls available on this sound card")
        return 0
    
    if args.get_headphone:
        volume, control_name = get_headphone_volume()
        if volume is not None:
            print(f"Headphone volume: {volume}% (control: {control_name})")
            return 0
        else:
            print("Error: No headphone volume controls available", file=sys.stderr)
            return 1
    
    if args.set_headphone:
        result = set_headphone_volume(args.set_headphone)
        if result:
            print(f"Headphone volume set to {args.set_headphone}")
            return 0
        else:
            print("Error: Failed to set headphone volume", file=sys.stderr)
            return 1
    
    if args.store_headphone:
        result = store_headphone_volume()
        if result:
            print("Headphone volume stored successfully")
            return 0
        else:
            print("Error: Failed to store headphone volume", file=sys.stderr)
            return 1
    
    if args.restore_headphone:
        result = restore_headphone_volume()
        if result:
            print("Headphone volume restored successfully")
            return 0
        else:
            print("Error: Failed to restore headphone volume", file=sys.stderr)
            return 1
    
    # Execute main command
    if args.store:
        result = store_volume()
    elif args.restore:
        result = restore_volume()
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())