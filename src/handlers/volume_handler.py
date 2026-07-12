#!/usr/bin/env python3
"""
Volume Handler for HiFiBerry Configuration API

Provides API endpoints for managing ALSA volume controls including headphone volume.
"""

import logging
from typing import Dict, Any, Optional, Union, cast
from flask import request, jsonify, Response
from ..volume import (  # type: ignore[import-untyped]
    get_available_headphone_controls,
    get_headphone_volume,
    set_headphone_volume,  # type: ignore[assignment]
    store_headphone_volume,
    restore_headphone_volume
)

logger = logging.getLogger(__name__)


class VolumeHandler:
    """Handler for volume-related API operations"""
    
    def __init__(self) -> None:
        """Initialize the volume handler"""
        pass
    
    def handle_list_headphone_controls(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/volume/headphone/controls - List available headphone volume controls
        
        Returns:
            JSON response with list of available headphone controls
        """
        try:
            controls: Any = get_available_headphone_controls()  # type: ignore[arg-type]
            
            return jsonify({  # type: ignore[return-value]
                "status": "success",
                "data": {
                    "controls": controls,
                    "count": len(controls)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing headphone controls: {e}")
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to list headphone controls",
                "error": str(e)
            }), 500
    
    def handle_get_headphone_volume(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/volume/headphone - Get current headphone volume
        
        Returns:
            JSON response with current headphone volume
        """
        try:
            volume, control_name = get_headphone_volume()  # type: ignore[arg-type]
            
            if volume is not None:
                return jsonify({  # type: ignore[return-value]
                    "status": "success",
                    "data": {
                        "volume": int(volume),
                        "control": control_name
                    }
                })
            else:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error getting headphone volume: {e}")
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to get headphone volume",
                "error": str(e)
            }), 500
    
    def handle_set_headphone_volume(self) -> 'Union[Response, tuple[Response, int]]':
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
            data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
            if not data:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400
            
            volume: Optional[Any] = data.get('volume')
            if volume is None:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "volume parameter is required"
                }), 400
            
            # Validate volume range
            try:
                volume_int: int = int(volume)
                if volume_int < 0 or volume_int > 100:
                    return jsonify({  # type: ignore[return-value]
                        "status": "error",
                        "message": "Volume must be between 0 and 100"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "Volume must be a valid integer"
                }), 400
            
            # Set the volume
            result: bool = set_headphone_volume(str(volume_int))  # type: ignore[arg-type]
            
            if result:
                return jsonify({  # type: ignore[return-value]
                    "status": "success",
                    "message": f"Headphone volume set to {volume_int}%",
                    "data": {
                        "volume": volume_int
                    }
                })
            else:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error setting headphone volume: {e}")
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to set headphone volume",
                "error": str(e)
            }), 500
    
    def handle_store_headphone_volume(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/volume/headphone/store - Store current headphone volume
        
        Returns:
            JSON response with success/error status
        """
        try:
            result: bool = store_headphone_volume()  # type: ignore[arg-type]
            
            if result:
                return jsonify({  # type: ignore[return-value]
                    "status": "success",
                    "message": "Headphone volume stored successfully"
                })
            else:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "No headphone volume controls available on this sound card"
                }), 404
                
        except Exception as e:
            logger.error(f"Error storing headphone volume: {e}")
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to store headphone volume",
                "error": str(e)
            }), 500
    
    def handle_restore_headphone_volume(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/volume/headphone/restore - Restore stored headphone volume
        
        Returns:
            JSON response with success/error status
        """
        try:
            result: bool = restore_headphone_volume()  # type: ignore[arg-type]
            
            if result:
                return jsonify({  # type: ignore[return-value]
                    "status": "success",
                    "message": "Headphone volume restored successfully"
                })
            else:
                return jsonify({  # type: ignore[return-value]
                    "status": "error",
                    "message": "No headphone volume settings found or no compatible controls available"
                }), 404
                
        except Exception as e:
            logger.error(f"Error restoring headphone volume: {e}")
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to restore headphone volume",
                "error": str(e)
            }), 500