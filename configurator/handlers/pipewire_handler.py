#!/usr/bin/env python3
"""
PipeWire Handler for HiFiBerry Configuration API

Provides API endpoints for managing PipeWire volume controls and settings.
"""

import logging
from flask import request, jsonify
from .. import pipewire

logger = logging.getLogger(__name__)


class PipewireHandler:
    """Handler for PipeWire-related API operations"""
    
    def __init__(self):
        """Initialize the PipeWire handler"""
        self.settings_manager = None  # Will be set by server
        pass
    
    def set_settings_manager(self, settings_manager):
        """Set the settings manager for auto-saving volumes"""
        self.settings_manager = settings_manager
    
    def handle_list_controls(self):
        """
        Handle GET /api/v1/pipewire/controls - List all available PipeWire volume controls
        
        Returns:
            JSON response with list of PipeWire controls
        """
        try:
            controls = pipewire.get_volume_controls()
            return jsonify({
                'status': 'success',
                'data': {
                    'controls': controls,
                    'count': len(controls)
                }
            })
        except Exception as e:
            logger.error(f"Error getting PipeWire controls: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_default_sink(self):
        """
        Handle GET /api/v1/pipewire/default-sink - Get the default PipeWire sink
        
        Returns:
            JSON response with the default sink information
        """
        try:
            default_sink = pipewire.get_default_sink()
            if default_sink:
                return jsonify({
                    'status': 'success',
                    'data': {
                        'default_sink': default_sink
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
        except Exception as e:
            logger.error(f"Error getting default sink: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_default_source(self):
        """
        Handle GET /api/v1/pipewire/default-source - Get the default PipeWire source
        
        Returns:
            JSON response with the default source information
        """
        try:
            default_source = pipewire.get_default_source()
            if default_source:
                return jsonify({
                    'status': 'success',
                    'data': {
                        'default_source': default_source
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'No default source found'
                }), 404
        except Exception as e:
            logger.error(f"Error getting default source: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_volume(self, control):
        """
        Handle GET /api/v1/pipewire/volume/<control> - Get volume for a PipeWire control
        
        Args:
            control: Control name (can be "default" for default sink)
            
        Returns:
            JSON response with volume information (both linear and dB)
        """
        try:
            # Handle "default" or empty control name
            if control == 'default' or control == '':
                default_sink = pipewire.get_default_sink()
                if not default_sink:
                    return jsonify({
                        'status': 'error',
                        'message': 'No default sink found'
                    }), 404
                control = default_sink
            
            # Get linear volume (0.0-1.0)
            volume = pipewire.get_volume(control)
            if volume is None:
                return jsonify({
                    'status': 'error',
                    'message': f'Control "{control}" not found'
                }), 404
            
            # Get dB volume
            volume_db = pipewire.get_volume_db(control)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'control': control,
                    'volume': volume,
                    'volume_db': volume_db
                }
            })
        except Exception as e:
            logger.error(f"Error getting volume for {control}: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_set_volume(self, control):
        """
        Handle PUT/POST /api/v1/pipewire/volume/<control> - Set volume for a PipeWire control
        
        Args:
            control: Control name (can be "default" for default sink)
            
        Returns:
            JSON response with updated volume information
        """
        try:
            # Handle "default" or empty control name
            if control == 'default' or control == '':
                default_sink = pipewire.get_default_sink()
                if not default_sink:
                    return jsonify({
                        'status': 'error',
                        'message': 'No default sink found'
                    }), 404
                control = default_sink
                resolved_default = True
            else:
                resolved_default = False
            
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            success = False
            
            # Check if volume_db is provided
            if 'volume_db' in data:
                try:
                    volume_db = float(data['volume_db'])
                    success = pipewire.set_volume_db(control, volume_db)
                except ValueError:
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid volume_db value'
                    }), 400
            
            # Check if volume (linear) is provided
            elif 'volume' in data:
                try:
                    volume = float(data['volume'])
                    if not 0.0 <= volume <= 1.0:
                        return jsonify({
                            'status': 'error',
                            'message': 'Volume must be between 0.0 and 1.0'
                        }), 400
                    success = pipewire.set_volume(control, volume)
                except ValueError:
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid volume value'
                    }), 400
            
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Either "volume" or "volume_db" must be provided'
                }), 400
            
            if success:
                # Return current volume values
                new_volume = pipewire.get_volume(control)
                new_volume_db = pipewire.get_volume_db(control)
                
                # Auto-save if this is the default sink and settings manager is available
                self._auto_save_if_default_sink(control, resolved_default)
                
                return jsonify({
                    'status': 'success',
                    'data': {
                        'control': control,
                        'volume': new_volume,
                        'volume_db': new_volume_db
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to set volume for control "{control}"'
                }), 500
                
        except Exception as e:
            logger.error(f"Error setting volume for {control}: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    def _auto_save_if_default_sink(self, control, resolved_default=False):
        """
        Automatically save the volume if the control is the default sink
        
        Args:
            control: The control that was modified
            resolved_default: True if control was resolved from "default" parameter
        """
        try:
            if self.settings_manager is None:
                return
                
            # If we already resolved from "default", we know this is the default sink
            if resolved_default:
                should_save = True
            else:
                # Get the default sink to compare
                default_sink = pipewire.get_default_sink()
                should_save = default_sink and control == default_sink
                
            if should_save:
                # This was a change to the default sink, auto-save it
                success = self.settings_manager.save_setting('pipewire_default_volume')
                if success:
                    logger.info(f"Auto-saved default PipeWire volume after change to {control}")
                else:
                    logger.warning(f"Failed to auto-save default PipeWire volume after change to {control}")
        except Exception as e:
            logger.error(f"Error auto-saving default volume: {e}")
