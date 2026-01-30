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
import requests
from flask import Flask, request, jsonify, make_response
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
from typing import Dict, Any, Optional
try:
    from waitress import serve
    WAITRESS_AVAILABLE = True
except ImportError:
    WAITRESS_AVAILABLE = False

# Import the ConfigDB class
from .configdb import ConfigDB
from .handlers import SystemdHandler, SMBHandler, HostnameHandler, SoundcardHandler, SystemHandler, FilesystemHandler, ScriptHandler, NetworkHandler, I2CHandler, VolumeHandler, BluetoothHandler
from .systeminfo import SystemInfo
from ._version import __version__
from .settings_manager import SettingsManager

# Set up logging
logger = logging.getLogger(__name__)

class ConfigAPIServer:
    """REST API server for HiFiBerry configuration services"""
    
    def __init__(self, host='0.0.0.0', port=1081, debug=False, no_waitress=False):
        """
        Initialize the API server
        
        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (default: 1081)
            debug: Enable debug mode
            no_waitress: Disable Waitress, use Flask server instead
        """
        logger.info("ConfigAPIServer.__init__: Starting initialization")
        self.host = host
        self.port = port
        self.debug = debug
        self.no_waitress = no_waitress
        
        logger.info("ConfigAPIServer.__init__: Creating Flask app")
        self.app = Flask(__name__)
        
        logger.info("ConfigAPIServer.__init__: Creating ConfigDB")
        self.configdb = ConfigDB()
        
        logger.info("ConfigAPIServer.__init__: Creating SystemInfo")
        self.systeminfo = SystemInfo()
        
        # Initialize all handlers
        logger.info("ConfigAPIServer.__init__: Initializing handlers")
        self.systemd_handler = SystemdHandler()
        self.smb_handler = SMBHandler()
        self.hostname_handler = HostnameHandler()
        self.soundcard_handler = SoundcardHandler()
        self.system_handler = SystemHandler()
        self.filesystem_handler = FilesystemHandler()
        self.script_handler = ScriptHandler()
        self.network_handler = NetworkHandler()
        self.i2c_handler = I2CHandler()
        self.volume_handler = VolumeHandler()
        self.bluetooth_handler = BluetoothHandler()
            
        logger.info("ConfigAPIServer.__init__: Creating SettingsManager")
        self.settings_manager = SettingsManager(self.configdb)
        
        # Configure Flask logging
        if not debug:
            self.app.logger.setLevel(logging.WARNING)
        
        # Register API routes
        logger.info("ConfigAPIServer.__init__: Registering routes")
        self._register_routes()
        
        # Register settings for modules
        logger.info("ConfigAPIServer.__init__: Registering module settings")
        self._register_module_settings()
        
        logger.info("ConfigAPIServer.__init__: Initialization complete")
    
    def _register_module_settings(self):
        """Register settings that should be saved/restored by modules"""
        pass
    
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
                    'soundcard_detection': '/api/v1/soundcard/detection',
                    'soundcard_detection_enable': '/api/v1/soundcard/detection/enable',
                    'soundcard_detection_disable': '/api/v1/soundcard/detection/disable',
                    'system_reboot': '/api/v1/system/reboot',
                    'system_shutdown': '/api/v1/system/shutdown',
                    'filesystem_symlinks': '/api/v1/filesystem/symlinks',
                    'filesystem_file_exists': '/api/v1/filesystem/file-exists',
                    'scripts': '/api/v1/scripts',
                    'script_info': '/api/v1/scripts/<script_id>',
                    'script_execute': '/api/v1/scripts/<script_id>/execute',
                    'network': '/api/v1/network',
                    'i2c_devices': '/api/v1/i2c/devices',
                    'bluetooth_settings': '/api/v1/bluetooth/settings',
                    'bluetooth_paired_devices': '/api/v1/bluetooth/paired-devices',
                    'bluetooth_passkey': '/api/v1/bluetooth/passkey',
                    'bluetooth_modal': '/api/v1/bluetooth/modal',
                    'bluetooth_unpair': '/api/v1/bluetooth/unpair',
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

        @self.app.route('/api/v1/soundcard/detection', methods=['GET'])
        def get_detection_status():
            """Get sound card detection enabled/disabled status"""
            return self.soundcard_handler.handle_detection_status()

        @self.app.route('/api/v1/soundcard/detection/enable', methods=['POST'])
        def enable_detection():
            """Enable sound card detection"""
            return self.soundcard_handler.handle_enable_detection()

        @self.app.route('/api/v1/soundcard/detection/disable', methods=['POST'])
        def disable_detection():
            """Disable sound card detection"""
            return self.soundcard_handler.handle_disable_detection()

        # Volume endpoints
        @self.app.route('/api/v1/volume/headphone/controls', methods=['GET'])
        def list_headphone_controls():
            """List available headphone volume controls"""
            return self.volume_handler.handle_list_headphone_controls()

        @self.app.route('/api/v1/volume/headphone', methods=['GET'])
        def get_headphone_volume():
            """Get current headphone volume"""
            return self.volume_handler.handle_get_headphone_volume()

        @self.app.route('/api/v1/volume/headphone', methods=['POST'])
        def set_headphone_volume():
            """Set headphone volume"""
            return self.volume_handler.handle_set_headphone_volume()

        @self.app.route('/api/v1/volume/headphone/store', methods=['POST'])
        def store_headphone_volume():
            """Store current headphone volume"""
            return self.volume_handler.handle_store_headphone_volume()

        @self.app.route('/api/v1/volume/headphone/restore', methods=['POST'])
        def restore_headphone_volume():
            """Restore stored headphone volume"""
            return self.volume_handler.handle_restore_headphone_volume()

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
        
        @self.app.route('/api/v1/filesystem/file-exists', methods=['POST'])
        def check_file_exists():
            """Check if a file or directory exists at a given path"""
            return self.filesystem_handler.handle_file_exists()

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

        # Bluetooth endpoints
        @self.app.route('/api/v1/bluetooth/settings', methods=['GET'])
        def get_bluetooth_settings():
            """Get bluetooth settings"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_get_bluetooth_settings()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/settings', methods=['POST'])
        def set_bluetooth_settings():
            """Set bluetooth settings"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_set_bluetooth_settings()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/paired-devices', methods=['GET'])
        def get_paired_devices():
            """Get paired bluetooth devices"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_get_paired_devices()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/unpair', methods=['POST'])
        def unpair_bluetooth_device():
            """Unpair a bluetooth device"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_unpair_device()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/passkey', methods=['GET'])
        def get_bluetooth_passkey():
            """Get and clear the stored Bluetooth passkey"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_get_bluetooth_passkey()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/passkey', methods=['POST'])
        def set_bluetooth_passkey():
            """Store a Bluetooth passkey"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_set_bluetooth_passkey()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/modal', methods=['GET'])
        def get_bluetooth_modal():
            """Get and clear the stored Bluetooth modal"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_get_show_modal()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503

        @self.app.route('/api/v1/bluetooth/modal', methods=['POST'])
        def set_bluetooth_modal():
            """Store a Bluetooth modal"""
            if self.bluetooth_handler:
                return self.bluetooth_handler.handle_set_show_modal()
            return jsonify({'status': 'error', 'message': 'Bluetooth handler not available'}), 503




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
            if WAITRESS_AVAILABLE and not self.debug and not self.no_waitress:
                # Use Waitress production server (prevents thread exhaustion)
                logger.info("Using Waitress WSGI server (production mode)")
                
                thread_count = 6
                logger.info(f"Waitress configuration: threads={thread_count}, host={self.host}, port={self.port}")
                
                serve(
                    self.app,
                    host=self.host,
                    port=self.port,
                    threads=thread_count,
                    channel_timeout=60,
                    cleanup_interval=10
                )
            else:
                # Fall back to Flask development server
                if not WAITRESS_AVAILABLE:
                    logger.warning("Waitress not available, using Flask development server (not recommended for production)")
                else:
                    logger.info("Using Flask development server (debug mode)")
                self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=self.debug,
                    threaded=True
                )
        except Exception as e:
            import traceback
            logger.error(f"Failed to start server: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
    parser.add_argument('--no-waitress', action='store_true',
                        help='Disable Waitress, use Flask development server instead')
    
    return parser.parse_args()

def main():
    """Main function"""
    # Add early logging to stderr before anything else
    import sys
    print("config-server: main() called", file=sys.stderr, flush=True)
    
    try:
        print("config-server: Starting initialization...", file=sys.stderr, flush=True)
        
        args = parse_arguments()
        
        print(f"config-server: Arguments parsed - port={args.port}", file=sys.stderr, flush=True)
        
        # Configure logging
        setup_logging(args.verbose)
        
        logger.info("Starting HiFiBerry Configuration Server")
        logger.info(f"Version: {__version__}")
        logger.info(f"Host: {args.host}, Port: {args.port}")
        
        # Create the server
        logger.info("Creating server instance...")
        server = ConfigAPIServer(
            host=args.host,
            port=args.port,
            debug=args.debug,
            no_waitress=args.no_waitress
        )
        logger.info("Server instance created successfully")
    except Exception as e:
        import traceback
        print(f"config-server: FATAL ERROR during initialization: {e}", file=sys.stderr, flush=True)
        print(f"config-server: Traceback:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        sys.exit(1)
    
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
