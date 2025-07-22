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
