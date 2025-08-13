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

    def handle_get_filtergraph(self):
        """Handle GET /api/v1/pipewire/filtergraph - Return PipeWire graph in DOT format.

        Returns plain text (text/plain) response with GraphViz DOT content.
        """
        try:
            dot = pipewire.get_filtergraph_dot()
            if dot is None:
                return jsonify({
                    'status': 'error',
                    'message': 'pw-dot command failed or not available'
                }), 500
            # Flask shortcut: return (response_text, status, headers)
            return dot, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        except Exception as e:
            logger.error(f"Error generating PipeWire filtergraph: {e}")
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

    # ------------------------------------------------------------------
    # Monostereo and balance endpoints (separate)
    # ------------------------------------------------------------------
    def handle_get_monostereo(self):
        """Handle GET monostereo mode"""
        try:
            mode = pipewire.get_monostereo()
            if mode is None:
                return jsonify({'status': 'error', 'message': 'Monostereo status unavailable'}), 503
            return jsonify({
                'status': 'success',
                'data': {
                    'monostereo_mode': mode
                }
            })
        except Exception as e:
            logger.error(f"Error getting monostereo: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_get_balance(self):
        """Handle GET balance"""
        try:
            balance = pipewire.get_balance()
            if balance is None:
                return jsonify({'status': 'error', 'message': 'Balance status unavailable'}), 503
            return jsonify({
                'status': 'success',
                'data': {
                    'balance': balance
                }
            })
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

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
            
            mode = data.get('mode')
            if mode is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode must be provided'
                }), 400
            
            # Apply monostereo mode
            ok = pipewire.set_monostereo(mode)
            if not ok:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set monostereo mode'
                }), 400
            
            # Get current status for response (only monostereo)
            current_mode = pipewire.get_monostereo()
            
            # Auto-save mixer state if settings manager present
            try:
                if self.settings_manager:
                    self.settings_manager.save_setting('pipewire_mixer_state')
            except Exception as e:
                logger.warning(f"Auto-save mixer state failed after monostereo set: {e}")
            
            return jsonify({
                'status': 'success',
                'data': {
                    'monostereo_mode': current_mode
                }
            })
        except Exception as e:
            logger.error(f"Error setting monostereo: {e}")
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
            
            balance = data.get('balance')
            if balance is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Balance must be provided'
                }), 400
            
            # Validate balance
            try:
                balance = float(balance)
                if not -1.0 <= balance <= 1.0:
                    return jsonify({
                        'status': 'error',
                        'message': 'Balance must be between -1.0 and 1.0'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': 'Balance must be a number'
                }), 400
            
            # Apply balance
            ok = pipewire.set_balance(balance)
            if not ok:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set balance'
                }), 400
            
            # Get current status for response (only balance)
            current_balance = pipewire.get_balance()
            
            # Auto-save mixer state if settings manager present
            try:
                if self.settings_manager:
                    self.settings_manager.save_setting('pipewire_mixer_state')
            except Exception as e:
                logger.warning(f"Auto-save mixer state failed after balance set: {e}")
            
            return jsonify({
                'status': 'success',
                'data': {
                    'balance': current_balance
                }
            })
        except Exception as e:
            logger.error(f"Error setting balance: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    def handle_get_mixer(self):
        try:
            gains = pipewire.get_mixer_status()
            if gains is None:
                return jsonify({'status': 'error', 'message': 'Mixer status unavailable'}), 503
            return jsonify({'status': 'success', 'data': {'gains': gains}})
        except Exception as e:
            logger.error(f"Error getting mixer status: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_get_mixer_mode(self):
        """Analyze mixer gains and return inferred monostereo mode and balance."""
        try:
            analysis = pipewire.analyze_mixer()
            if analysis is None:
                return jsonify({'status': 'error', 'message': 'Mixer analysis unavailable'}), 503
            gains = pipewire.get_mixer_status() or {}
            return jsonify({
                'status': 'success', 
                'data': {
                    'monostereo_mode': analysis.get('monostereo_mode'), 
                    'balance': analysis.get('balance'), 
                    'gains': gains
                }
            })
        except Exception as e:
            logger.error(f"Error analyzing mixer: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ------------------------------------------------------------------
    # EQ endpoints
    # ------------------------------------------------------------------
    def handle_get_eq(self, eq_num):
        """Handle GET EQ filter parameters"""
        try:
            # Validate EQ number
            try:
                eq_number = int(eq_num)
                if not 1 <= eq_number <= 16:
                    return jsonify({
                        'status': 'error',
                        'message': 'EQ filter number must be between 1 and 16'
                    }), 400
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': 'EQ filter number must be a valid number'
                }), 400
                
            eq_params = pipewire.get_eq(eq_number)
            if eq_params is None:
                return jsonify({'status': 'error', 'message': 'EQ status unavailable'}), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'eq': eq_number,
                    'freq': eq_params['freq'],
                    'q': eq_params['q'],
                    'gain': eq_params['gain']
                }
            })
        except Exception as e:
            logger.error(f"Error getting EQ {eq_num}: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_get_eq_all(self):
        """Handle GET all EQ filter parameters"""
        try:
            eq_filters = pipewire.get_eq_all()
            if eq_filters is None:
                return jsonify({'status': 'error', 'message': 'EQ status unavailable'}), 503
                
            return jsonify({
                'status': 'success',
                'data': {
                    'eq_filters': eq_filters
                }
            })
        except Exception as e:
            logger.error(f"Error getting all EQ filters: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_set_eq(self, eq_num):
        """Handle SET EQ filter parameters"""
        try:
            # Validate EQ number
            try:
                eq_number = int(eq_num)
                if not 1 <= eq_number <= 16:
                    return jsonify({
                        'status': 'error',
                        'message': 'EQ filter number must be between 1 and 16'
                    }), 400
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': 'EQ filter number must be a valid number'
                }), 400
                
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            # Extract parameters (all optional - only provided ones will be updated)
            freq = data.get('freq')
            q = data.get('q')
            gain = data.get('gain')
            
            if freq is None and q is None and gain is None:
                return jsonify({
                    'status': 'error',
                    'message': 'At least one parameter (freq, q, gain) must be provided'
                }), 400
            
            # Validate parameters if provided
            if freq is not None:
                try:
                    freq_val = float(freq)
                    if not 20 <= freq_val <= 20000:
                        return jsonify({
                            'status': 'error',
                            'message': 'Frequency must be between 20 and 20000 Hz'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': 'Frequency must be a number'
                    }), 400
            else:
                freq_val = None
                
            if q is not None:
                try:
                    q_val = float(q)
                    if not 0.1 <= q_val <= 20.0:
                        return jsonify({
                            'status': 'error',
                            'message': 'Q factor must be between 0.1 and 20.0'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': 'Q factor must be a number'
                    }), 400
            else:
                q_val = None
                
            if gain is not None:
                try:
                    gain_val = float(gain)
                    if not -15.0 <= gain_val <= 15.0:
                        return jsonify({
                            'status': 'error',
                            'message': 'Gain must be between -15.0 and +15.0 dB'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': 'Gain must be a number'
                    }), 400
            else:
                gain_val = None
            
            # Apply EQ parameters
            ok = pipewire.set_eq(eq_number, freq_val, q_val, gain_val)
            if not ok:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set EQ filter parameters'
                }), 400
            
            # Get current parameters for response
            current_params = pipewire.get_eq(eq_number)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'eq': eq_number,
                    'freq': current_params['freq'],
                    'q': current_params['q'],
                    'gain': current_params['gain']
                }
            })
        except Exception as e:
            logger.error(f"Error setting EQ {eq_num}: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_set_eq_all(self):
        """Handle SET all EQ filter parameters"""
        try:
            # Get JSON data from request
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'JSON data required'
                }), 400
            
            eq_filters = data.get('eq_filters')
            if eq_filters is None:
                return jsonify({
                    'status': 'error',
                    'message': 'EQ filters must be provided'
                }), 400
            
            # Validate EQ filters data
            if not isinstance(eq_filters, dict):
                return jsonify({
                    'status': 'error',
                    'message': 'EQ filters must be a dict mapping EQ numbers to parameter dicts'
                }), 400
            
            # Validate each EQ filter and its parameters
            validated_filters = {}
            for eq_str, params in eq_filters.items():
                try:
                    eq_number = int(eq_str)
                    if not 1 <= eq_number <= 16:
                        return jsonify({
                            'status': 'error',
                            'message': f'EQ filter {eq_number} must be between 1 and 16'
                        }), 400
                except ValueError:
                    return jsonify({
                        'status': 'error',
                        'message': f'EQ filter "{eq_str}" must be a valid number'
                    }), 400
                
                if not isinstance(params, dict):
                    return jsonify({
                        'status': 'error',
                        'message': f'Parameters for EQ {eq_number} must be a dict'
                    }), 400
                
                # Check required parameters
                for key in ['freq', 'q', 'gain']:
                    if key not in params:
                        return jsonify({
                            'status': 'error',
                            'message': f'EQ {eq_number} missing required parameter: {key}'
                        }), 400
                
                # Validate frequency
                try:
                    freq_val = float(params['freq'])
                    if not 20 <= freq_val <= 20000:
                        return jsonify({
                            'status': 'error',
                            'message': f'Frequency for EQ {eq_number} must be between 20 and 20000 Hz'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': f'Frequency for EQ {eq_number} must be a number'
                    }), 400
                
                # Validate Q factor
                try:
                    q_val = float(params['q'])
                    if not 0.1 <= q_val <= 20.0:
                        return jsonify({
                            'status': 'error',
                            'message': f'Q factor for EQ {eq_number} must be between 0.1 and 20.0'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': f'Q factor for EQ {eq_number} must be a number'
                    }), 400
                
                # Validate gain
                try:
                    gain_val = float(params['gain'])
                    if not -15.0 <= gain_val <= 15.0:
                        return jsonify({
                            'status': 'error',
                            'message': f'Gain for EQ {eq_number} must be between -15.0 and +15.0 dB'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 'error',
                        'message': f'Gain for EQ {eq_number} must be a number'
                    }), 400
                
                validated_filters[eq_number] = {
                    'freq': freq_val,
                    'q': q_val,
                    'gain': gain_val
                }
            
            # Apply EQ filters
            ok = pipewire.set_eq_all(validated_filters)
            if not ok:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set EQ filters'
                }), 400
            
            # Get current filters for response
            current_filters = pipewire.get_eq_all()
            
            return jsonify({
                'status': 'success',
                'data': {
                    'eq_filters': current_filters
                }
            })
        except Exception as e:
            logger.error(f"Error setting EQ filters: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_reset_eq(self):
        """Handle EQ reset to default values"""
        try:
            # Reset all filters to defaults (freq from config, Q=1.0, gain=0dB)
            default_freqs = [32.0, 50.0, 80.0, 125.0, 200.0, 315.0, 500.0, 800.0,
                             1250.0, 2000.0, 3150.0, 5000.0, 8000.0, 10000.0, 16000.0, 20000.0]
            reset_filters = {}
            for eq_num in range(1, 17):
                reset_filters[eq_num] = {
                    'freq': default_freqs[eq_num - 1] if eq_num <= len(default_freqs) else 1000.0,
                    'q': 1.0,
                    'gain': 0.0
                }
            
            ok = pipewire.set_eq_all(reset_filters)
            if not ok:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to reset EQ'
                }), 400
            
            # Get current filters for response
            current_filters = pipewire.get_eq_all()
            
            return jsonify({
                'status': 'success',
                'data': {
                    'eq_filters': current_filters
                }
            })
        except Exception as e:
            logger.error(f"Error resetting EQ: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
