#!/usr/bin/env python3
"""
Soundcard Handler for HiFiBerry Configuration API

Provides API endpoints for managing sound card configurations.
"""

import logging
from flask import request, jsonify
from ..soundcard import SOUND_CARD_DEFINITIONS
from ..configtxt import ConfigTxt

logger = logging.getLogger(__name__)


class SoundcardHandler:
    """Handler for soundcard-related API operations"""
    
    def __init__(self):
        """Initialize the soundcard handler"""
        pass
    
    def handle_list_soundcards(self):
        """
        Handle GET /api/v1/soundcards - List all available sound cards
        
        Returns:
            JSON response with list of sound cards and their properties
        """
        try:
            soundcards_list = []
            
            for card_name, attributes in SOUND_CARD_DEFINITIONS.items():
                soundcard_info = {
                    "name": card_name,
                    "dtoverlay": attributes.get("dtoverlay", "unknown"),
                    "volume_control": attributes.get("volume_control"),
                    "headphone_volume_control": attributes.get("headphone_volume_control"),
                    "output_channels": attributes.get("output_channels", 0),
                    "input_channels": attributes.get("input_channels", 0),
                    "features": attributes.get("features", []),
                    "supports_dsp": attributes.get("supports_dsp", False),
                    "card_type": attributes.get("card_type", []),
                    "is_pro": attributes.get("is_pro", False)
                }
                soundcards_list.append(soundcard_info)
            
            return jsonify({
                "status": "success",
                "data": {
                    "soundcards": soundcards_list,
                    "count": len(soundcards_list)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing soundcards: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to list soundcards",
                "error": str(e)
            }), 500
    
    def handle_set_dtoverlay(self):
        """
        Handle POST /api/v1/soundcard/dtoverlay - Set device tree overlay in config.txt
        
        Expected JSON payload:
        {
            "dtoverlay": "hifiberry-dac",
            "remove_existing": true  # optional, defaults to true
        }
        
        Returns:
            JSON response with success/error status
        """
        try:
            # Parse JSON request
            data = request.get_json()
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            dtoverlay = data.get('dtoverlay')
            if not dtoverlay:
                return jsonify({
                    "status": "error",
                    "message": "dtoverlay parameter is required"
                }), 400
            
            remove_existing = data.get('remove_existing', True)
            
            # Validate that the dtoverlay exists in our sound card definitions
            valid_overlays = [attrs.get('dtoverlay') for attrs in SOUND_CARD_DEFINITIONS.values()]
            if dtoverlay not in valid_overlays:
                return jsonify({
                    "status": "error",
                    "message": f"Invalid dtoverlay '{dtoverlay}'. Must be one of the supported HiFiBerry overlays.",
                    "valid_overlays": sorted(list(set(valid_overlays)))
                }), 400
            
            # Initialize ConfigTxt handler
            config = ConfigTxt()
            
            # Remove existing HiFiBerry overlays if requested
            if remove_existing:
                config.remove_hifiberry_overlays()
            
            # Add the new overlay
            config.enable_overlay(dtoverlay)
            
            # Save changes
            config.save()
            
            if config.changes_made:
                message = f"Successfully set dtoverlay to '{dtoverlay}'"
                if remove_existing:
                    message += " (removed existing HiFiBerry overlays)"
                
                return jsonify({
                    "status": "success",
                    "message": message,
                    "data": {
                        "dtoverlay": dtoverlay,
                        "changes_made": True,
                        "reboot_required": True
                    }
                })
            else:
                return jsonify({
                    "status": "success",
                    "message": f"dtoverlay '{dtoverlay}' was already configured",
                    "data": {
                        "dtoverlay": dtoverlay,
                        "changes_made": False,
                        "reboot_required": False
                    }
                })
                
        except FileNotFoundError as e:
            logger.error(f"Config file not found: {e}")
            return jsonify({
                "status": "error",
                "message": "Config file not found",
                "error": str(e)
            }), 404
            
        except Exception as e:
            logger.error(f"Error setting dtoverlay: {e}")
            return jsonify({
                "status": "error", 
                "message": "Failed to set dtoverlay",
                "error": str(e)
            }), 500

    def handle_detection_status(self):
        """
        Handle GET /api/v1/soundcard/detection - Get detection status
        
        Returns:
            JSON response with detection enabled/disabled status
        """
        try:
            config = ConfigTxt()
            is_disabled = config.is_detection_disabled()
            
            return jsonify({
                "status": "success",
                "data": {
                    "detection_enabled": not is_disabled,
                    "detection_disabled": is_disabled
                }
            })
            
        except Exception as e:
            logger.error(f"Error checking detection status: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to check detection status",
                "error": str(e)
            }), 500

    def handle_enable_detection(self):
        """
        Handle POST /api/v1/soundcard/detection/enable - Enable sound card detection
        
        This will also remove any HiFiBerry overlays from config.txt to allow auto-detection
        
        Returns:
            JSON response with success/error status
        """
        try:
            config = ConfigTxt()
            was_disabled = config.is_detection_disabled()
            
            # Remove HiFiBerry overlays to enable auto-detection
            config.remove_hifiberry_overlays()
            
            # Enable detection
            config.enable_detection()
            config.save()
            
            if was_disabled or config.changes_made:
                return jsonify({
                    "status": "success",
                    "message": "Sound card detection enabled and fixed overlays removed",
                    "data": {
                        "detection_enabled": True,
                        "changes_made": config.changes_made,
                        "reboot_required": True
                    }
                })
            else:
                return jsonify({
                    "status": "success",
                    "message": "Sound card detection was already enabled",
                    "data": {
                        "detection_enabled": True,
                        "changes_made": False,
                        "reboot_required": False
                    }
                })
                
        except Exception as e:
            logger.error(f"Error enabling detection: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to enable sound card detection",
                "error": str(e)
            }), 500

    def handle_disable_detection(self):
        """
        Handle POST /api/v1/soundcard/detection/disable - Disable sound card detection
        
        Expected JSON payload (optional):
        {
            "card_name": "Beocreate 4-Channel Amplifier"  # Sets fixed sound card by name
        }
        
        If card_name is provided, sets the appropriate dtoverlay and disables detection.
        If card_name is not provided, only disables detection (keeps existing overlay).
        
        Returns:
            JSON response with success/error status
        """
        try:
            config = ConfigTxt()
            was_enabled = not config.is_detection_disabled()
            
            # Check if a card name was provided in the request
            data = request.get_json() if request.is_json else {}
            card_name = data.get('card_name') if data else None
            
            if card_name:
                # Look up the card definition to get the dtoverlay
                card_def = SOUND_CARD_DEFINITIONS.get(card_name)
                if not card_def:
                    return jsonify({
                        "status": "error",
                        "message": f"Unknown sound card: '{card_name}'",
                        "available_cards": list(SOUND_CARD_DEFINITIONS.keys())
                    }), 400
                
                dtoverlay = card_def.get('dtoverlay')
                if not dtoverlay:
                    return jsonify({
                        "status": "error",
                        "message": f"Sound card '{card_name}' does not have a dtoverlay defined"
                    }), 400
                
                # Remove existing HiFiBerry overlays and set the new one
                config.remove_hifiberry_overlays()
                config.disable_detection()
                config.disable_eeprom()
                config.enable_overlay(dtoverlay, card_name=card_name)
                config.save()
                
                return jsonify({
                    "status": "success",
                    "message": f"Fixed sound card set to '{card_name}' with overlay '{dtoverlay}'",
                    "data": {
                        "card_name": card_name,
                        "dtoverlay": dtoverlay,
                        "detection_enabled": False,
                        "changes_made": config.changes_made,
                        "reboot_required": True
                    }
                })
            else:
                # No card name provided, just disable detection
                config.disable_detection()
                config.save()
                
                if was_enabled:
                    return jsonify({
                        "status": "success",
                        "message": "Sound card detection disabled",
                        "data": {
                            "detection_enabled": False,
                            "changes_made": config.changes_made
                        }
                    })
                else:
                    return jsonify({
                        "status": "success",
                        "message": "Sound card detection was already disabled",
                        "data": {
                            "detection_enabled": False,
                            "changes_made": False
                        }
                    })
                
        except Exception as e:
            logger.error(f"Error disabling detection: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to disable sound card detection",
                "error": str(e)
            }), 500

    def handle_detect_soundcard(self):
        """
        Handle GET /api/v1/soundcard/detect - Detect current sound card
        
        Returns:
            JSON response with detected sound card name and dtoverlay
        """
        try:
            from ..soundcard import Soundcard
            
            soundcard = Soundcard()
            
            if soundcard.name:
                # Get the sound card definition
                card_def = SOUND_CARD_DEFINITIONS.get(soundcard.name)
                dtoverlay = card_def.get("dtoverlay") if card_def else "unknown"
                
                return jsonify({
                    "status": "success",
                    "message": "Sound card detected successfully",
                    "data": {
                        "card_name": soundcard.name,
                        "dtoverlay": dtoverlay,
                        "volume_control": soundcard.volume_control,
                        "headphone_volume_control": soundcard.headphone_volume_control,
                        "hardware_index": soundcard.get_hardware_index(),
                        "output_channels": soundcard.output_channels,
                        "input_channels": soundcard.input_channels,
                        "features": soundcard.features,
                        "hat_name": soundcard.hat_name,
                        "supports_dsp": soundcard.supports_dsp,
                        "card_type": soundcard.card_type,
                        "card_detected": True,
                        "definition_found": card_def is not None
                    }
                })
            else:
                return jsonify({
                    "status": "success",
                    "message": "No sound card detected",
                    "data": {
                        "card_name": None,
                        "dtoverlay": None,
                        "card_detected": False,
                        "definition_found": False
                    }
                })
                
        except Exception as e:
            logger.error(f"Error detecting soundcard: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to detect sound card",
                "error": str(e)
            }), 500
