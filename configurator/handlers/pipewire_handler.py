#!/usr/bin/env python3
"""
PipeWire Handler for HiFiBerry Configuration API

Provides API endpoints for managing PipeWire volume controls and settings.
Directly uses PipeWire Python module for audio operations.
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
            if controls is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'controls': controls,
                    'count': len(controls)
                }
            })
        except Exception as e:
            logger.error(f"Error listing PipeWire controls: {e}")
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
            if default_sink is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'default_sink': default_sink
                }
            })
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
            if default_source is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'default_source': default_source
                }
            })
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
            # Handle "default" control
            if control == 'default' or control == '':
                control = pipewire.get_default_sink()
                if not control:
                    return jsonify({
                        'status': 'error',
                        'message': 'No default sink found'
                    }), 404
            
            # Get volume (linear percentage)
            volume = pipewire.get_volume(control)
            if volume is None:
                return jsonify({
                    'status': 'error',
                    'message': f'Control "{control}" not found'
                }), 404
            
            # Get volume in dB
            volume_db = pipewire.get_volume_db(control)
            
            response_data = {
                'control': control,
                'volume': volume
            }
            
            if volume_db is not None:
                response_data['volume_db'] = volume_db
            
            return jsonify({
                'status': 'success',
                'data': response_data
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
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            # Handle "default" control
            if control == 'default' or control == '':
                control = pipewire.get_default_sink()
                if not control:
                    return jsonify({
                        'status': 'error',
                        'message': 'No default sink found'
                    }), 404
            
            # Set volume using appropriate method
            if 'volume_db' in data:
                result = pipewire.set_volume_db(control, data['volume_db'])
                if result is None:
                    return jsonify({
                        'status': 'error',
                        'message': f'Control "{control}" not found'
                    }), 404
                    
                # Get updated volume for response
                volume = pipewire.get_volume(control)
                volume_db = data['volume_db']
                
            elif 'volume' in data:
                volume = data['volume']
                if not isinstance(volume, (int, float)) or volume < 0 or volume > 100:
                    return jsonify({
                        'status': 'error',
                        'message': 'Volume must be between 0 and 100'
                    }), 400
                    
                result = pipewire.set_volume(control, volume)
                if result is None:
                    return jsonify({
                        'status': 'error',
                        'message': f'Control "{control}" not found'
                    }), 404
                    
                # Get volume in dB for response
                volume_db = pipewire.get_volume_db(control)
                
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Volume level required (volume or volume_db)'
                }), 400
            
            # Auto-save if settings manager is available
            if self.settings_manager:
                try:
                    self.settings_manager.set_value(f'pipewire.volume.{control}', volume)
                    self.settings_manager.save()
                except Exception as e:
                    logger.warning(f"Failed to auto-save volume setting: {e}")
            
            response_data = {
                'control': control,
                'volume': volume
            }
            
            if volume_db is not None:
                response_data['volume_db'] = volume_db
            
            return jsonify({
                'status': 'success',
                'data': response_data
            })
            
        except Exception as e:
            logger.error(f"Error setting volume for {control}: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500


    def handle_get_filtergraph(self):
        """Handle GET /api/v1/pipewire/filtergraph - Return PipeWire graph in DOT format.

        Returns plain text (text/plain) response with GraphViz DOT content.
        """
        try:
            dot_graph = pipewire.get_filtergraph_dot()
            if dot_graph is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return dot_graph, 200, {'Content-Type': 'text/plain; charset=utf-8'}
            
        except Exception as e:
            logger.error(f"Error getting filtergraph: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    # ------------------------------------------------------------------
    # Monostereo and balance endpoints (separate)
    # ------------------------------------------------------------------
    def handle_get_monostereo(self):
        """Handle GET monostereo mode"""
        try:
            mode = pipewire.get_monostereo()
            if mode is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'monostereo_mode': mode
                }
            })
        except Exception as e:
            logger.error(f"Error getting monostereo mode: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_balance(self):
        """Handle GET balance"""
        try:
            balance = pipewire.get_balance()
            if balance is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'balance': balance
                }
            })
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_set_monostereo(self):
        """Handle monostereo mode setting"""
        try:
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            if 'mode' not in data:
                return jsonify({
                    'status': 'error',
                    'message': 'Monostereo mode required'
                }), 400
                
            mode = data['mode']
            result = pipewire.set_monostereo(mode)
            if result is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set monostereo mode'
                }), 500
            
            # Auto-save mixer state if settings manager present
            if self.settings_manager:
                try:
                    self.settings_manager.set_value('pipewire.monostereo_mode', mode)
                    self.settings_manager.save()
                except Exception as e:
                    logger.warning(f"Failed to auto-save monostereo setting: {e}")
            
            return jsonify({
                'status': 'success',
                'data': {
                    'monostereo_mode': mode
                }
            })
            
        except Exception as e:
            logger.error(f"Error setting monostereo mode: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_set_balance(self):
        """Handle balance setting"""
        try:
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            if 'balance' not in data:
                return jsonify({
                    'status': 'error',
                    'message': 'Balance value required'
                }), 400
                
            balance = data['balance']
            if not isinstance(balance, (int, float)) or balance < -1.0 or balance > 1.0:
                return jsonify({
                    'status': 'error',
                    'message': 'Balance must be between -1.0 and 1.0'
                }), 400
                
            result = pipewire.set_balance(balance)
            if result is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set balance'
                }), 500
            
            # Auto-save mixer state if settings manager present
            if self.settings_manager:
                try:
                    self.settings_manager.set_value('pipewire.balance', balance)
                    self.settings_manager.save()
                except Exception as e:
                    logger.warning(f"Failed to auto-save balance setting: {e}")
            
            return jsonify({
                'status': 'success',
                'data': {
                    'balance': balance
                }
            })
            
        except Exception as e:
            logger.error(f"Error setting balance: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_mixer_mode(self):
        """Analyze mixer gains and return inferred monostereo mode and balance."""
        try:
            # Get monostereo mode and balance
            monostereo_mode = pipewire.get_monostereo()
            balance = pipewire.get_balance()
            gains = pipewire.get_mixer_status()
            
            if monostereo_mode is None and balance is None:
                return jsonify({
                    'status': 'error',
                    'message': 'PipeWire daemon not available'
                }), 503
            
            return jsonify({
                'status': 'success', 
                'data': {
                    'monostereo_mode': monostereo_mode, 
                    'balance': balance, 
                    'gains': gains or {}
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting mixer mode: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_debug_info(self):
        """Handle GET /api/v1/pipewire/debug - Get debugging information for PipeWire commands"""
        try:
            debug_info = pipewire.get_wpctl_debug_info()
            return jsonify({
                'status': 'success',
                'data': debug_info
            })
        except Exception as e:
            logger.error(f"Error getting debug info: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
