#!/usr/bin/env python3
"""
HiFiBerry Configuration API Server

A REST API server that provides access to the HiFiBerry configuration database
and other system configuration services.
"""

import os
import sys
import json
import logging
import argparse
from flask import Flask, request, jsonify, make_response
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
from typing import Dict, Any, Optional

# Import the ConfigDB class
from .configdb import ConfigDB
from .handlers import SystemdHandler, SMBHandler, HostnameHandler, SoundcardHandler, SystemHandler, FilesystemHandler, ScriptHandler, NetworkHandler, I2CHandler, PipewireHandler
from .systeminfo import SystemInfo
from ._version import __version__
from .settings_manager import SettingsManager

# Set up logging
logger = logging.getLogger(__name__)

class ConfigAPIServer:
    """REST API server for HiFiBerry configuration services"""
    
    def __init__(self, host='0.0.0.0', port=1081, debug=False):
        """
        Initialize the API server
        
        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (default: 1081)
            debug: Enable debug mode
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.app = Flask(__name__)
        self.configdb = ConfigDB()
        self.systemd_handler = SystemdHandler()
        self.systeminfo = SystemInfo()
        self.smb_handler = SMBHandler()
        self.hostname_handler = HostnameHandler()
        self.soundcard_handler = SoundcardHandler()
        self.system_handler = SystemHandler()
        self.filesystem_handler = FilesystemHandler()
        self.script_handler = ScriptHandler()
        self.network_handler = NetworkHandler()
        self.i2c_handler = I2CHandler()
        self.pipewire_handler = PipewireHandler()
        self.settings_manager = SettingsManager(self.configdb)
        
        # Set settings manager on handlers that need it
        self.pipewire_handler.set_settings_manager(self.settings_manager)
        
        # Configure Flask logging
        if not debug:
            self.app.logger.setLevel(logging.WARNING)
        
        # Register API routes
        self._register_routes()
        
        # Register settings for modules
        self._register_module_settings()
    
    def _register_module_settings(self):
        """Register settings that should be saved/restored by modules"""
        # Register PipeWire default volume setting
        self.settings_manager.register_setting(
            "pipewire_default_volume",
            self._save_pipewire_default_volume,
            self._restore_pipewire_default_volume
        )
        # Register PipeWire mixer state (mode/balance) setting
        self.settings_manager.register_setting(
            "pipewire_mixer_state",
            self._save_pipewire_mixer_state,
            self._restore_pipewire_mixer_state
        )
    
    def _save_pipewire_default_volume(self):
        """Save current default PipeWire volume"""
        try:
            from . import pipewire
            default_sink = pipewire.get_default_sink()
            if default_sink:
                volume = pipewire.get_volume(default_sink)
                if volume is not None:
                    logger.info(f"Saving PipeWire default volume: {volume}")
                    return volume
            return None
        except Exception as e:
            logger.error(f"Error saving PipeWire default volume: {e}")
            return None
    
    def _restore_pipewire_default_volume(self, value):
        """Restore default PipeWire volume"""
        try:
            from . import pipewire
            default_sink = pipewire.get_default_sink()
            if default_sink:
                volume = float(value)
                if 0.0 <= volume <= 1.0:
                    success = pipewire.set_volume(default_sink, volume)
                    if success:
                        logger.info(f"Restored PipeWire default volume to: {volume}")
                    else:
                        logger.error(f"Failed to restore PipeWire default volume to: {volume}")
                else:
                    logger.error(f"Invalid volume value for restore: {volume}")
            else:
                logger.error("No default sink found for volume restore")
        except Exception as e:
            logger.error(f"Error restoring PipeWire default volume: {e}")

    def _save_pipewire_mixer_state(self):
        """Save current monostereo mode and balance state encoded as 'monostereo_mode,balance'."""
        try:
            from . import pipewire
            monostereo_mode = pipewire.get_monostereo()
            balance = pipewire.get_balance()
            if monostereo_mode is None or monostereo_mode == 'unknown':
                return None
            if balance is None:
                balance = 0.0
            # Round balance for stability
            balance = max(-1.0, min(1.0, balance))
            encoded = f"{monostereo_mode},{balance:.6f}"
            logger.info(f"Saving PipeWire mixer state: {encoded}")
            return encoded
        except Exception as e:
            logger.error(f"Error saving PipeWire mixer state: {e}")
            return None

    def _restore_pipewire_mixer_state(self, value):
        """Restore monostereo mode and balance from encoded 'monostereo_mode,balance' string."""
        try:
            from . import pipewire
            if not value:
                return False
            parts = str(value).split(',')
            if len(parts) != 2:
                logger.warning(f"Invalid mixer state format: {value}")
                return False
            monostereo_mode = parts[0].strip()
            try:
                balance = float(parts[1])
            except Exception:
                balance = 0.0
            
            success = True
            discrete_modes = {'mono','stereo','left','right'}
            
            # Set monostereo mode
            if monostereo_mode in discrete_modes:
                success &= pipewire.set_monostereo(monostereo_mode)
                logger.info(f"Restored PipeWire monostereo mode: {monostereo_mode}")
            else:
                logger.warning(f"Unknown saved monostereo mode '{monostereo_mode}', skipping restore")
                return False
            
            # Set balance (only if non-zero)
            if abs(balance) > 0.001:
                success &= pipewire.set_balance(balance)
                logger.info(f"Restored PipeWire balance: {balance}")
            
            if not success:
                logger.error(f"Failed to restore PipeWire mixer state: mode={monostereo_mode} balance={balance}")
            
            return success
        except Exception as e:
            logger.error(f"Error restoring PipeWire mixer state: {e}")
            return False
    
    def restore_settings(self):
        """Restore all registered settings from configdb"""
        logger.info("Restoring saved settings...")
        results = self.settings_manager.restore_all_settings()
        return results
    
    def _register_routes(self):
        """Register all API routes"""
        
        # Version endpoint
        @self.app.route('/version', methods=['GET'])
        @self.app.route('/api/v1/version', methods=['GET'])
        def get_version():
            """Get version information"""
            return jsonify({
                'service': 'hifiberry-config-api',
                'version': __version__,
                'api_version': 'v1',
                'description': 'HiFiBerry Configuration Server',
                'endpoints': {
                    'version': '/version',
                    'systeminfo': '/api/v1/systeminfo',
                    'keys': '/api/v1/keys',
                    'key': '/api/v1/key/<key>',
                    'systemd_services': '/api/v1/systemd/services',
                    'systemd_service': '/api/v1/systemd/service/<service>',
                    'systemd_service_exists': '/api/v1/systemd/service/<service>/exists',
                    'systemd_operation': '/api/v1/systemd/service/<service>/<operation>',
                    'smb_servers': '/api/v1/smb/servers',
                    'smb_server_test': '/api/v1/smb/test/<server>',
                    'smb_shares': '/api/v1/smb/shares',
                    'smb_mounts': '/api/v1/smb/mounts',
                    'smb_mount_config': '/api/v1/smb/mount',
                    'smb_mount_all': '/api/v1/smb/mount-all',
                    'hostname': '/api/v1/hostname',
                    'soundcards': '/api/v1/soundcards',
                    'soundcard_dtoverlay': '/api/v1/soundcard/dtoverlay',
                    'soundcard_detect': '/api/v1/soundcard/detect',
                    'system_reboot': '/api/v1/system/reboot',
                    'system_shutdown': '/api/v1/system/shutdown',
                    'filesystem_symlinks': '/api/v1/filesystem/symlinks',
                    'scripts': '/api/v1/scripts',
                    'script_info': '/api/v1/scripts/<script_id>',
                    'script_execute': '/api/v1/scripts/<script_id>/execute',
                    'network': '/api/v1/network',
                    'i2c_devices': '/api/v1/i2c/devices',
                    'pipewire_controls': '/api/v1/pipewire/controls',
                    'pipewire_default_sink': '/api/v1/pipewire/default-sink',
                    'pipewire_default_source': '/api/v1/pipewire/default-source',
                    'pipewire_volume': '/api/v1/pipewire/volume/<control>',
                    'pipewire_volume_set': '/api/v1/pipewire/volume/<control>',
                    'pipewire_filtergraph': '/api/v1/pipewire/filtergraph',
                    'pipewire_mixer_analysis': '/api/v1/pipewire/mixer/analysis',
                    'pipewire_monostereo_get': '/api/v1/pipewire/monostereo',
                    'pipewire_monostereo_set': '/api/v1/pipewire/monostereo',
                    'pipewire_balance_get': '/api/v1/pipewire/balance',
                    'pipewire_balance_set': '/api/v1/pipewire/balance',
                    'pipewire_save_default_volume': '/api/v1/pipewire/save-default-volume',
                    'settings_list': '/api/v1/settings',
                    'settings_save': '/api/v1/settings/save',
                    'settings_restore': '/api/v1/settings/restore'
                }
            })
        
        # System information endpoint
        @self.app.route('/api/v1/systeminfo', methods=['GET'])
        def get_system_info():
            """Get system information including Pi model and HAT info"""
            try:
                info = self.systeminfo.get_system_info_dict()
                return jsonify(info)
            except Exception as e:
                logger.error(f"Error getting system info: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to retrieve system information',
                    'error': str(e)
                }), 500
        
        # Configuration endpoints using configdb handlers
        @self.app.route('/api/v1/keys', methods=['GET'])
        def get_config_keys():
            """Get all configuration keys"""
            return self.configdb.handle_get_config_keys()
        
        @self.app.route('/api/v1/key/<key>', methods=['GET'])
        def get_config_value(key):
            """Get a specific configuration value"""
            return self.configdb.handle_get_config_value(key)
        
        @self.app.route('/api/v1/key/<key>', methods=['PUT', 'POST'])
        def set_config_value(key):
            """Set a configuration value"""
            return self.configdb.handle_set_config_value(key)
        
        @self.app.route('/api/v1/key/<key>', methods=['DELETE'])
        def delete_config_value(key):
            """Delete a configuration value"""
            return self.configdb.handle_delete_config_value(key)
        
        # Systemd endpoints
        @self.app.route('/api/v1/systemd/services', methods=['GET'])
        def list_systemd_services():
            """List all configured systemd services and their permissions"""
            return self.systemd_handler.handle_list_services()
        
        @self.app.route('/api/v1/systemd/service/<service>', methods=['GET'])
        def get_systemd_service_status(service):
            """Get detailed status of a systemd service"""
            return self.systemd_handler.handle_systemd_status(service)
        
        @self.app.route('/api/v1/systemd/service/<service>/exists', methods=['GET'])
        def check_service_exists(service):
            """Check if a systemd service exists on the system"""
            return self.systemd_handler.handle_service_exists(service)
        
        @self.app.route('/api/v1/systemd/service/<service>/<operation>', methods=['POST'])
        def execute_systemd_operation(service, operation):
            """Execute a systemd operation on a service"""
            return self.systemd_handler.handle_systemd_operation(service, operation)
        
        # SMB/CIFS endpoints
        @self.app.route('/api/v1/smb/servers', methods=['GET'])
        def list_smb_servers():
            """List all SMB servers on the network"""
            return self.smb_handler.handle_list_servers()
        
        @self.app.route('/api/v1/smb/test/<server>', methods=['POST'])
        def test_smb_connection(server):
            """Test connection to an SMB server"""
            return self.smb_handler.handle_test_connection(server)
        
        @self.app.route('/api/v1/smb/shares', methods=['POST'])
        def list_smb_shares():
            """List shares on an SMB server"""
            return self.smb_handler.handle_list_shares()
        
        @self.app.route('/api/v1/smb/mounts', methods=['GET'])
        def list_smb_mounts():
            """List all configured SMB mounts"""
            return self.smb_handler.handle_list_mounts()
        
        @self.app.route('/api/v1/smb/mount', methods=['POST'])
        def manage_smb_mount():
            """Create or remove SMB share configuration based on action parameter"""
            return self.smb_handler.handle_manage_mount()

        @self.app.route('/api/v1/smb/mount-all', methods=['POST'])
        def mount_all_samba_shares():
            """Mount all configured Samba shares via systemd service"""
            return self.smb_handler.handle_mount_all_samba()

        # Hostname endpoints
        @self.app.route('/api/v1/hostname', methods=['GET'])
        def get_hostname():
            """Get current system and pretty hostnames"""
            return self.hostname_handler.handle_get_hostname()
        
        @self.app.route('/api/v1/hostname', methods=['POST'])
        def set_hostname():
            """Set system hostname and/or pretty hostname"""
            return self.hostname_handler.handle_set_hostname()

        # Soundcard endpoints
        @self.app.route('/api/v1/soundcards', methods=['GET'])
        def list_soundcards():
            """List all available HiFiBerry sound cards"""
            return self.soundcard_handler.handle_list_soundcards()
        
        @self.app.route('/api/v1/soundcard/dtoverlay', methods=['POST'])
        def set_dtoverlay():
            """Set device tree overlay for sound card configuration"""
            return self.soundcard_handler.handle_set_dtoverlay()

        @self.app.route('/api/v1/soundcard/detect', methods=['GET'])
        def detect_soundcard():
            """Detect current sound card and return name and dtoverlay"""
            return self.soundcard_handler.handle_detect_soundcard()

        # System endpoints
        @self.app.route('/api/v1/system/reboot', methods=['POST'])
        def reboot_system():
            """Reboot the system with optional delay"""
            return self.system_handler.handle_reboot()
        
        @self.app.route('/api/v1/system/shutdown', methods=['POST'])
        def shutdown_system():
            """Shutdown the system with optional delay"""
            return self.system_handler.handle_shutdown()

        # Filesystem endpoints
        @self.app.route('/api/v1/filesystem/symlinks', methods=['POST'])
        def list_symlinks():
            """List all symlinks in a given directory including their destinations"""
            return self.filesystem_handler.handle_list_symlinks()

        # Script endpoints
        @self.app.route('/api/v1/scripts', methods=['GET'])
        def list_scripts():
            """List all configured scripts"""
            return self.script_handler.handle_list_scripts()
        
        @self.app.route('/api/v1/scripts/<script_id>', methods=['GET'])
        def get_script_info(script_id):
            """Get information about a specific script"""
            return self.script_handler.handle_get_script_info(script_id)
        
        @self.app.route('/api/v1/scripts/<script_id>/execute', methods=['POST'])
        def execute_script(script_id):
            """Execute a configured script"""
            return self.script_handler.handle_execute_script(script_id)

        # Network configuration endpoint
        @self.app.route('/api/v1/network', methods=['GET'])
        def get_network_config():
            """Get network configuration including hostname and interface details"""
            return self.network_handler.handle_get_network_config()

        # I2C device scan endpoint
        @self.app.route('/api/v1/i2c/devices', methods=['GET'])
        def get_i2c_devices():
            """Scan I2C bus for devices"""
            return self.i2c_handler.handle_get_i2c_devices()

        # PipeWire endpoints
        @self.app.route('/api/v1/pipewire/controls', methods=['GET'])
        def list_pipewire_controls():
            """List all available PipeWire volume controls"""
            return self.pipewire_handler.handle_list_controls()

        @self.app.route('/api/v1/pipewire/default-sink', methods=['GET'])
        def get_default_sink():
            """Get the default PipeWire sink"""
            return self.pipewire_handler.handle_get_default_sink()

        @self.app.route('/api/v1/pipewire/default-source', methods=['GET'])
        def get_default_source():
            """Get the default PipeWire source"""
            return self.pipewire_handler.handle_get_default_source()

        @self.app.route('/api/v1/pipewire/volume/<path:control>', methods=['GET'])
        def get_pipewire_volume(control):
            """Get volume for a PipeWire control, returns both linear and dB values"""
            return self.pipewire_handler.handle_get_volume(control)

        @self.app.route('/api/v1/pipewire/volume/<path:control>', methods=['PUT', 'POST'])
        def set_pipewire_volume(control):
            """Set volume for a PipeWire control, accepts both linear (volume) and dB (volume_db) values"""
            return self.pipewire_handler.handle_set_volume(control)

        @self.app.route('/api/v1/pipewire/save-default-volume', methods=['POST'])
        def save_pipewire_default_volume():
            """Save the current default PipeWire volume to settings"""
            try:
                success = self.settings_manager.save_setting('pipewire_default_volume')
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': 'Default PipeWire volume saved successfully',
                        'data': {
                            'setting': 'pipewire_default_volume',
                            'saved': True
                        }
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to save default PipeWire volume'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error saving default volume: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        @self.app.route('/api/v1/pipewire/filtergraph', methods=['GET'])
        def get_pipewire_filtergraph():
            """Get the PipeWire filter/connection graph in GraphViz DOT format (text/plain)."""
            return self.pipewire_handler.handle_get_filtergraph()

        # PipeWire mixer / balance endpoints
        @self.app.route('/api/v1/pipewire/mixer/analysis', methods=['GET'])
        def get_pipewire_mixer_analysis():
            """Get inferred monostereo mode and balance plus gains"""
            return self.pipewire_handler.handle_get_mixer_mode()

        @self.app.route('/api/v1/pipewire/monostereo', methods=['GET'])
        def get_pipewire_monostereo():
            """Get current monostereo mode"""
            return self.pipewire_handler.handle_get_monostereo()

        @self.app.route('/api/v1/pipewire/monostereo', methods=['POST'])
        def set_pipewire_monostereo():
            """Set monostereo mode (stereo/mono/left/right)"""
            return self.pipewire_handler.handle_set_monostereo()

        @self.app.route('/api/v1/pipewire/balance', methods=['GET'])
        def get_pipewire_balance():
            """Get current balance"""
            return self.pipewire_handler.handle_get_balance()

        @self.app.route('/api/v1/pipewire/balance', methods=['POST'])
        def set_pipewire_balance():
            """Set balance (-1 to 1)"""
            return self.pipewire_handler.handle_set_balance()

        @self.app.route('/api/v1/pipewire/mixer/set', methods=['POST'])
        def set_pipewire_mixer():
            """DEPRECATED: Set mixer mode and/or balance in one operation. Use separate monostereo and balance endpoints."""
            return self.pipewire_handler.handle_set_mixer()

        # Settings management endpoints
        @self.app.route('/api/v1/settings/save', methods=['POST'])
        def save_settings():
            """Save current settings to configdb"""
            try:
                results = self.settings_manager.save_all_settings()
                successful = sum(results.values())
                total = len(results)
                
                return jsonify({
                    'status': 'success',
                    'message': f'Saved {successful}/{total} settings',
                    'data': {
                        'results': results,
                        'successful': successful,
                        'total': total
                    }
                })
            except Exception as e:
                logger.error(f"Error saving settings: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        @self.app.route('/api/v1/settings/restore', methods=['POST'])
        def restore_settings():
            """Restore settings from configdb"""
            try:
                results = self.settings_manager.restore_all_settings()
                successful = sum(results.values())
                total = len(results)
                
                return jsonify({
                    'status': 'success',
                    'message': f'Restored {successful}/{total} settings',
                    'data': {
                        'results': results,
                        'successful': successful,
                        'total': total
                    }
                })
            except Exception as e:
                logger.error(f"Error restoring settings: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        @self.app.route('/api/v1/settings', methods=['GET'])
        def list_settings():
            """List registered and saved settings"""
            try:
                registered = self.settings_manager.list_registered_settings()
                saved = self.settings_manager.list_saved_settings()
                
                return jsonify({
                    'status': 'success',
                    'data': {
                        'registered_settings': registered,
                        'saved_settings': saved,
                        'registered_count': len(registered),
                        'saved_count': len(saved)
                    }
                })
            except Exception as e:
                logger.error(f"Error listing settings: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        # Error handlers
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'status': 'error',
                'message': 'Bad request'
            }), 400
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'status': 'error',
                'message': 'Resource not found'
            }), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                'status': 'error',
                'message': 'Internal server error'
            }), 500
    
    def run(self):
        """Start the API server"""
        logger.info(f"Starting HiFiBerry Configuration Server on {self.host}:{self.port}")
        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            sys.exit(1)

def setup_logging(verbose=False):
    """Configure logging"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    root_logger.addHandler(console_handler)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='HiFiBerry Configuration Server')
    
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=1081,
                        help='Port to listen on (default: 1081)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--restore-settings', action='store_true',
                        help='Restore saved settings from configdb on startup')
    parser.add_argument('--auto-restore-settings', action='store_true',
                        help='Automatically restore saved settings during normal startup')
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    # Configure logging
    setup_logging(args.verbose)
    
    # Create the server
    server = ConfigAPIServer(
        host=args.host,
        port=args.port,
        debug=args.debug
    )
    
    # Restore settings if requested (standalone mode)
    if args.restore_settings:
        logger.info("Restoring settings...")
        results = server.restore_settings()
        successful = sum(results.values())
        total = len(results)
        logger.info(f"Settings restoration completed: {successful}/{total} successful")
        
        # Always exit successfully after attempting restore
        # This prevents systemd service failures when some settings can't be restored
        return 0
    
    # Auto-restore settings during normal startup if requested
    if args.auto_restore_settings:
        logger.info("Auto-restoring settings during startup...")
        try:
            results = server.restore_settings()
            successful = sum(results.values())
            total = len(results)
            logger.info(f"Auto-restore completed: {successful}/{total} successful")
        except Exception as e:
            logger.warning(f"Auto-restore failed, continuing with startup: {e}")
    
    # Start the server normally
    server.run()

if __name__ == "__main__":
    main()
