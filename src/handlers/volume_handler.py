#!/usr/bin/env python3
"""
Volume Handler for HiFiBerry Configuration API

Provides API endpoints for managing ALSA volume controls including headphone volume.
"""

import logging
from flask import request, jsonify
from ..volume import (
    get_available_headphone_controls,
    get_headphone_volume,
    set_headphone_volume,
    store_headphone_volume,
    restore_headphone_volume
)

logger = logging.getLogger(__name__)


class VolumeHandler:
    """Handler for volume-related API operations"""
    
    def __init__(self):
        """Initialize the volume handler"""
        pass
    
    def handle_list_headphone_controls(self):
        """
        Handle GET /api/v1/volume/headphone/controls - List available headphone volume controls
        
        Returns:
            JSON response with list of available headphone controls
        """
        try:
            controls = get_available_headphone_controls()
            
            return jsonify({
                "status": "success",
                "data": {
                    "controls": controls,
                    "count": len(controls)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing headphone controls: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to list headphone controls",
                "error": str(e)
            }), 500
    
    def handle_get_headphone_volume(self):
        """
        Handle GET /api/v1/volume/headphone - Get current headphone volume
        
        Returns:
            JSON response with current headphone volume
        """
        try:
            volume, control_name = get_headphone_volume()
            
            if volume is not None:
                return jsonify({
                    "status": "success",
                    "data": {
                        "volume": int(volume),
                        "control": control_name
                    }
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error getting headphone volume: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to get headphone volume",
                "error": str(e)
            }), 500
    
    def handle_set_headphone_volume(self):
        """
        Handle POST /api/v1/volume/headphone - Set headphone volume
        
        Expected JSON payload:
        {
            "volume": 50
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
            
            volume = data.get('volume')
            if volume is None:
                return jsonify({
                    "status": "error",
                    "message": "volume parameter is required"
                }), 400
            
            # Validate volume range
            try:
                volume_int = int(volume)
                if volume_int < 0 or volume_int > 100:
                    return jsonify({
                        "status": "error",
                        "message": "Volume must be between 0 and 100"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "status": "error",
                    "message": "Volume must be a valid integer"
                }), 400
            
            # Set the volume
            result = set_headphone_volume(str(volume_int))
            
            if result:
                return jsonify({
                    "status": "success",
                    "message": f"Headphone volume set to {volume_int}%",
                    "data": {
                        "volume": volume_int
                    }
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error setting headphone volume: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to set headphone volume",
                "error": str(e)
            }), 500
    
    def handle_store_headphone_volume(self):
        """
        Handle POST /api/v1/volume/headphone/store - Store current headphone volume
        
        Returns:
            JSON response with success/error status
        """
        try:
            result = store_headphone_volume()
            
            if result:
                return jsonify({
                    "status": "success",
                    "message": "Headphone volume stored successfully"
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error storing headphone volume: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to store headphone volume",
                "error": str(e)
            }), 500
    
    def handle_restore_headphone_volume(self):
        """
        Handle POST /api/v1/volume/headphone/restore - Restore stored headphone volume
        
        Returns:
            JSON response with success/error status
        """
        try:
            result = restore_headphone_volume()
            
            if result:
                return jsonify({
                    "status": "success",
                    "message": "Headphone volume restored successfully"
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "No headphone volume settings found or no compatible controls available"
                }), 404
                
        except Exception as e:
            logger.error(f"Error restoring headphone volume: {e}")
            return jsonify({
                "status": "error",
                "message": "Failed to restore headphone volume",
                "error": str(e)
            }), 500