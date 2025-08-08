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
from .handlers import SystemdHandler, SMBHandler, HostnameHandler, SoundcardHandler, SystemHandler, FilesystemHandler, ScriptHandler, NetworkHandler
from .systeminfo import SystemInfo
from ._version import __version__

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
        
        # Configure Flask logging
        if not debug:
            self.app.logger.setLevel(logging.WARNING)
        
        # Register API routes
        self._register_routes()
    
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
                    'network': '/api/v1/network'
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
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    # Configure logging
    setup_logging(args.verbose)
    
    # Create and start the server
    server = ConfigAPIServer(
        host=args.host,
        port=args.port,
        debug=args.debug
    )
    
    server.run()

if __name__ == "__main__":
    main()
