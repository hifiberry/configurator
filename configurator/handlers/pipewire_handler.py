#!/usr/bin/env python3
"""
PipeWire Handler for HiFiBerry Configuration API

Provides API endpoints for managing PipeWire volume controls and settings.
Uses HTTP proxy to communicate with user's PipeWire session via pipewire daemon.
"""

import logging
import requests
from flask import request, jsonify

logger = logging.getLogger(__name__)

# Default PipeWire daemon URL (runs as user session)
PIPEWIRE_DAEMON_URL = "http://localhost:1082"

class PipewireHandler:
    """Handler for PipeWire-related API operations"""
    
    def __init__(self):
        """Initialize the PipeWire handler"""
        self.settings_manager = None  # Will be set by server
        self.daemon_url = PIPEWIRE_DAEMON_URL
    
    def set_settings_manager(self, settings_manager):
        """Set the settings manager for auto-saving volumes"""
        self.settings_manager = settings_manager
    
    def _make_request(self, method, endpoint, data=None, timeout=5):
        """
        Make HTTP request to PipeWire daemon
        
        Args:
            method: HTTP method (GET, POST, PUT)
            endpoint: API endpoint (without /api/v1 prefix)
            data: Request data for POST/PUT
            timeout: Request timeout in seconds
            
        Returns:
            Response object or None if failed
        """
        try:
            url = f"{self.daemon_url}/api/v1{endpoint}"
            logger.debug(f"Making {method} request to {url}")
            
            if method == 'GET':
                response = requests.get(url, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, timeout=timeout)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None
                
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"PipeWire daemon request failed: {e}")
            return None
    
    def handle_list_controls(self):
        """
        Handle GET /api/v1/pipewire/controls - List all available PipeWire volume controls
        
        Returns:
            JSON response with list of PipeWire controls
        """
        response = self._make_request('GET', '/volume/controls')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                controls = data.get('data', [])
                return jsonify({
                    'status': 'success',
                    'data': {
                        'controls': controls,
                        'count': len(controls)
                    }
                })
        
        logger.error("Failed to get PipeWire controls from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503

    def handle_get_default_sink(self):
        """
        Handle GET /api/v1/pipewire/default-sink - Get the default PipeWire sink
        
        Returns:
            JSON response with the default sink information
        """
        response = self._make_request('GET', '/devices/default-sink')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                default_sink = data.get('data', {}).get('default_sink')
                return jsonify({
                    'status': 'success',
                    'data': {
                        'default_sink': default_sink
                    }
                })
        
        logger.error("Failed to get default sink from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503

    def handle_get_default_source(self):
        """
        Handle GET /api/v1/pipewire/default-source - Get the default PipeWire source
        
        Returns:
            JSON response with the default source information
        """
        response = self._make_request('GET', '/devices/default-source')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                default_source = data.get('data', {}).get('default_source')
                return jsonify({
                    'status': 'success',
                    'data': {
                        'default_source': default_source
                    }
                })
        
        logger.error("Failed to get default source from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503

    def handle_get_volume(self, control):
        """
        Handle GET /api/v1/pipewire/volume/<control> - Get volume for a PipeWire control
        
        Args:
            control: Control name (can be "default" for default sink)
            
        Returns:
            JSON response with volume information (both linear and dB)
        """
        # Handle "default" control
        if control == 'default' or control == '':
            default_response = self._make_request('GET', '/devices/default-sink')
            if not (default_response and default_response.status_code == 200):
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
            
            default_data = default_response.json()
            if not default_data.get('success'):
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
                
            control = default_data.get('data', {}).get('default_sink')
            if not control:
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
        
        # Get volume and volume_db
        volume_response = self._make_request('GET', f'/volume/{control}')
        volume_db_response = self._make_request('GET', f'/volume/{control}/db')
        
        if not (volume_response and volume_response.status_code == 200):
            return jsonify({
                'status': 'error',
                'message': f'Control "{control}" not found'
            }), 404
        
        volume_data = volume_response.json()
        volume_db_data = volume_db_response.json() if volume_db_response and volume_db_response.status_code == 200 else None
        
        if not volume_data.get('success'):
            return jsonify({
                'status': 'error',
                'message': f'Control "{control}" not found'
            }), 404
        
        volume = volume_data.get('data', {}).get('volume')
        volume_db = volume_db_data.get('data', {}).get('volume_db') if volume_db_data and volume_db_data.get('success') else None
        
        return jsonify({
            'status': 'success',
            'data': {
                'control': control,
                'volume': volume,
                'volume_db': volume_db
            }
        })

    def handle_set_volume(self, control):
        """
        Handle PUT/POST /api/v1/pipewire/volume/<control> - Set volume for a PipeWire control
        
        Args:
            control: Control name (can be "default" for default sink)
            
        Returns:
            JSON response with updated volume information
        """
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'JSON data required'
            }), 400
        
        # Handle "default" control
        resolved_default = False
        if control == 'default' or control == '':
            default_response = self._make_request('GET', '/devices/default-sink')
            if not (default_response and default_response.status_code == 200):
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
            
            default_data = default_response.json()
            if not default_data.get('success'):
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
                
            control = default_data.get('data', {}).get('default_sink')
            if not control:
                return jsonify({
                    'status': 'error',
                    'message': 'No default sink found'
                }), 404
            resolved_default = True
        
        # Set volume using daemon API
        if 'volume_db' in data:
            response = self._make_request('POST', f'/volume/{control}/db', {'volume_db': data['volume_db']})
        elif 'volume' in data:
            response = self._make_request('POST', f'/volume/{control}', {'volume': data['volume']})
        else:
            return jsonify({
                'status': 'error',
                'message': 'Either "volume" or "volume_db" must be provided'
            }), 400
        
        if response and response.status_code == 200:
            # Get updated values
            updated_response = self.handle_get_volume(control)
            if isinstance(updated_response, tuple):
                return updated_response
            
            # Auto-save if this affects the default sink
            self._auto_save_if_default_sink(control, data, resolved_default)
            return updated_response
        else:
            return jsonify({
                'status': 'error',
                'message': 'PipeWire daemon not available'
            }), 503

    def handle_get_filtergraph(self):
        """Handle GET /api/v1/pipewire/filtergraph - Return PipeWire graph in DOT format.

        Returns plain text (text/plain) response with GraphViz DOT content.
        """
        response = self._make_request('GET', '/graph/dot')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                dot_graph = data.get('data', {}).get('dot_graph', '')
                return dot_graph, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        
        logger.error("Failed to get filtergraph from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503
    
    def _auto_save_if_default_sink(self, control, data, resolved_default=False):
        """
        Automatically save the volume if the control is the default sink
        
        Args:
            control: The control that was modified
            data: The request data that was sent
            resolved_default: True if control was resolved from "default" parameter
        """
        try:
            if self.settings_manager is None:
                return
                
            # Check if control is "default" or try to get the default sink
            should_save = resolved_default
            if not should_save:
                # Get the default sink to compare
                response = self._make_request('GET', '/devices/default-sink')
                if response and response.status_code == 200:
                    sink_data = response.json()
                    if sink_data.get('success'):
                        default_sink = sink_data.get('data', {}).get('default_sink')
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

    # ------------------------------------------------------------------
    # Monostereo and balance endpoints (separate)
    # ------------------------------------------------------------------
    def handle_get_monostereo(self):
        """Handle GET monostereo mode"""
        response = self._make_request('GET', '/mixer/monostereo')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                mode = data.get('data', {}).get('mode')
                return jsonify({
                    'status': 'success',
                    'data': {
                        'monostereo_mode': mode
                    }
                })
        
        logger.error("Failed to get monostereo from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503

    def handle_get_balance(self):
        """Handle GET balance"""
        response = self._make_request('GET', '/mixer/balance')
        if response and response.status_code == 200:
            data = response.json()
            if data.get('success'):
                balance = data.get('data', {}).get('balance')
                return jsonify({
                    'status': 'success',
                    'data': {
                        'balance': balance
                    }
                })
        
        logger.error("Failed to get balance from daemon")
        return jsonify({
            'status': 'error',
            'message': 'PipeWire daemon not available'
        }), 503

    def handle_set_monostereo(self):
        """Handle monostereo mode setting"""
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'JSON data required'
            }), 400
        
        response = self._make_request('POST', '/mixer/monostereo', data)
        if response and response.status_code == 200:
            # Auto-save mixer state if settings manager present
            try:
                if self.settings_manager:
                    self.settings_manager.save_setting('pipewire_mixer_state')
            except Exception as e:
                logger.warning(f"Auto-save mixer state failed after monostereo set: {e}")
            
            # Get current mode for response
            current_response = self.handle_get_monostereo()
            return current_response
        else:
            logger.error("Failed to set monostereo via daemon")
            return jsonify({
                'status': 'error',
                'message': 'PipeWire daemon not available'
            }), 503

    def handle_set_balance(self):
        """Handle balance setting"""
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'JSON data required'
            }), 400
        
        response = self._make_request('POST', '/mixer/balance', data)
        if response and response.status_code == 200:
            # Auto-save mixer state if settings manager present
            try:
                if self.settings_manager:
                    self.settings_manager.save_setting('pipewire_mixer_state')
            except Exception as e:
                logger.warning(f"Auto-save mixer state failed after balance set: {e}")
            
            # Get current balance for response
            current_response = self.handle_get_balance()
            return current_response
        else:
            logger.error("Failed to set balance via daemon")
            return jsonify({
                'status': 'error',
                'message': 'PipeWire daemon not available'
            }), 503

    def handle_get_mixer_mode(self):
        """Analyze mixer gains and return inferred monostereo mode and balance."""
        # Get monostereo mode and balance
        mono_response = self._make_request('GET', '/mixer/monostereo')
        balance_response = self._make_request('GET', '/mixer/balance')
        mixer_response = self._make_request('GET', '/mixer/status')
        
        monostereo_mode = None
        balance = None
        gains = {}
        
        if mono_response and mono_response.status_code == 200:
            mono_data = mono_response.json()
            if mono_data.get('success'):
                monostereo_mode = mono_data.get('data', {}).get('mode')
        
        if balance_response and balance_response.status_code == 200:
            balance_data = balance_response.json()
            if balance_data.get('success'):
                balance = balance_data.get('data', {}).get('balance')
        
        if mixer_response and mixer_response.status_code == 200:
            mixer_data = mixer_response.json()
            if mixer_data.get('success'):
                gains = mixer_data.get('data', {})
        
        if monostereo_mode is None and balance is None:
            logger.error("Failed to get mixer analysis from daemon")
            return jsonify({
                'status': 'error',
                'message': 'PipeWire daemon not available'
            }), 503
        
        return jsonify({
            'status': 'success', 
            'data': {
                'monostereo_mode': monostereo_mode, 
                'balance': balance, 
                'gains': gains
            }
        })
