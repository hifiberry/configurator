#!/usr/bin/env python3

import logging
import subprocess
import json
import os
import tempfile
from flask import jsonify, request
from typing import Dict, List, Any, Optional, Tuple
import traceback

from ..sambaclient import (
    list_all_servers, 
    check_smb_connection, 
    list_smb_shares
)
from ..sambamount import (
    read_mount_config,
    add_mount_config,
    remove_mount_config,
    list_configured_mounts
)

logger = logging.getLogger(__name__)

# State file to track previously mounted shares
SAMBA_STATE_FILE = "/tmp/sambamount_state.json"

def load_mount_state() -> Dict[str, str]:
    """
    Load the previous mount state from the state file.
    Returns a dict mapping mount keys (server/share) to mountpoints.
    """
    try:
        if os.path.exists(SAMBA_STATE_FILE):
            with open(SAMBA_STATE_FILE, 'r') as f:
                state = json.load(f)
                logger.debug(f"Loaded mount state: {state}")
                return state
        else:
            logger.debug("No existing mount state file found")
            return {}
    except Exception as e:
        logger.warning(f"Failed to load mount state: {e}")
        return {}

def save_mount_state(mount_state: Dict[str, str]) -> None:
    """
    Save the current mount state to the state file.
    mount_state is a dict mapping mount keys (server/share) to mountpoints.
    """
    try:
        with open(SAMBA_STATE_FILE, 'w') as f:
            json.dump(mount_state, f, indent=2)
        logger.debug(f"Saved mount state: {mount_state}")
    except Exception as e:
        logger.error(f"Failed to save mount state: {e}")

def get_mount_key(server: str, share: str) -> str:
    """Generate a unique key for a server/share combination"""
    return f"{server}/{share}"

def unmount_share(mountpoint: str) -> bool:
    """
    Unmount a share at the given mountpoint.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"Unmounting {mountpoint}")
        result = subprocess.run(
            ['umount', mountpoint],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully unmounted {mountpoint}")
            return True
        else:
            logger.warning(f"Failed to unmount {mountpoint}: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error unmounting {mountpoint}: {e}")
        return False

class SMBHandler:
    """Handler for SMB/CIFS related API endpoints"""
    
    def __init__(self):
        """Initialize the SMB handler"""
        logger.debug("Initializing SMBHandler")
    
    def handle_list_servers(self) -> Dict[str, Any]:
        """
        Handle GET /api/v1/smb/servers
        List all SMB servers on the network
        """
        try:
            logger.debug("Listing SMB servers on network")
            servers = list_all_servers()
            
            return jsonify({
                'status': 'success',
                'data': {
                    'servers': servers,
                    'count': len(servers)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing SMB servers: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to list SMB servers',
                'error': str(e)
            }), 500
    
    def handle_test_connection(self, server: str) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/test/<server>
        Test connection to an SMB server
        """
        try:
            # Get authentication from POST body
            data = request.get_json() or {}
            username = data.get('username')
            password = data.get('password')
            
            # Server can be provided in request body or URL path
            # Request body takes precedence over URL path
            server_from_body = data.get('server')
            test_server = server_from_body if server_from_body else server
            
            logger.debug(f"Testing connection to SMB server: {test_server}")
            
            # Test connection
            connected, error_msg = check_smb_connection(
                server=test_server,
                username=username,
                password=password
            )
            
            if connected:
                return jsonify({
                    'status': 'success',
                    'data': {
                        'server': test_server,
                        'connected': True,
                        'message': 'Connection successful'
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Connection failed',
                    'data': {
                        'server': test_server,
                        'connected': False,
                        'error': error_msg or 'Unknown connection error'
                    }
                })
                
        except Exception as e:
            # Use the server from body if available, otherwise fall back to URL path
            data = request.get_json() or {}
            test_server = data.get('server', server)
            
            logger.error(f"Error testing connection to {test_server}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Internal server error',
                'data': {
                    'server': test_server,
                    'connected': False,
                    'error': str(e)
                }
            })
    
    def handle_list_shares(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/shares
        List shares on an SMB server
        """
        try:
            # Get all parameters from POST body
            data = request.get_json() or {}
            server = data.get('server')
            username = data.get('username')
            password = data.get('password')
            detailed = data.get('detailed', False)
            
            # Validate required parameters
            if not server:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required parameter: server'
                }), 400
            
            logger.debug(f"Listing shares on SMB server: {server}")
            
            # List shares
            shares, detected_version = list_smb_shares(
                server=server,
                username=username,
                password=password
            )
            
            # Convert shares to the expected format
            share_list = []
            for share in shares:
                share_info = {
                    'name': share.get('name', ''),
                    'type': share.get('type', 'Disk'),
                    'comment': share.get('comment', '')
                }
                if detailed:
                    share_info['size'] = share.get('size')
                    share_info['available'] = share.get('available')
                
                share_list.append(share_info)
            
            response_data = {
                'server': server,
                'shares': share_list,
                'count': len(share_list)
            }
            
            if detected_version:
                response_data['detected_version'] = detected_version
            
            return jsonify({
                'status': 'success',
                'data': response_data
            })
            
        except Exception as e:
            # Get server from request body
            data = request.get_json() or {}
            target_server = data.get('server', 'unknown')
            
            logger.error(f"Error listing shares on {target_server}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to list shares on {target_server}',
                'error': str(e)
            }), 500
    
    def handle_list_mounts(self) -> Dict[str, Any]:
        """
        Handle GET /api/v1/smb/mounts
        List all configured SMB mounts with mount status
        """
        try:
            logger.debug("Listing SMB mount configurations")
            
            # Use the existing function that already reads from ConfigDB and checks mount status
            mounts = list_configured_mounts()
            
            # Collect statistics
            mounted_count = 0
            unmounted_count = 0
            
            for mount in mounts:
                if mount.get('mounted', False):
                    mounted_count += 1
                else:
                    unmounted_count += 1
            
            return jsonify({
                'status': 'success',
                'data': {
                    'mounts': mounts,
                    'count': len(mounts),
                    'summary': {
                        'total': len(mounts),
                        'mounted': mounted_count,
                        'unmounted': unmounted_count
                    }
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing SMB mounts: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to list SMB mounts',
                'error': str(e)
            }), 500
    
    def handle_manage_mount(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/mount
        Create or remove SMB share configuration based on action parameter
        """
        try:
            # Get JSON data from request
            if not request.is_json:
                return jsonify({
                    'status': 'error',
                    'message': 'Content-Type must be application/json'
                }), 400
            
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing request body'
                }), 400
            
            # Validate action field
            action = data.get('action')
            if not action:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required field: action. Must be \'add\' or \'remove\''
                }), 400
            
            if action not in ['add', 'remove']:
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid action. Must be \'add\' or \'remove\''
                }), 400
            
            # Validate required fields
            server = data.get('server')
            share = data.get('share')
            
            if not server or not share:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required fields: action, server and share'
                }), 400
            
            if action == 'add':
                return self._handle_add_mount(data, server, share)
            else:  # action == 'remove'
                return self._handle_remove_mount(data, server, share)
                
        except Exception as e:
            logger.error(f"Error managing SMB mount: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to process SMB share configuration',
                'error': str(e),
                'details': 'An internal server error occurred while processing the mount configuration'
            }), 500
    
    def _handle_add_mount(self, data: Dict[str, Any], server: str, share: str) -> Dict[str, Any]:
        """Helper method to handle adding a mount configuration"""
        # Get optional fields
        mountpoint = data.get('mountpoint')
        user = data.get('user')
        password = data.get('password')
        version = data.get('version')
        options = data.get('options')
        
        logger.debug(f"Creating SMB mount configuration for {server}/{share}")
        
        # Add mount configuration (but don't mount it)
        success, error_msg = add_mount_config(
            server=server,
            share=share,
            mountpoint=mountpoint,
            user=user,
            password=password,
            version=version,
            options=options
        )
        
        if success:
            # Determine the actual mountpoint used
            final_mountpoint = mountpoint or f"/data/{server}-{share}"
            
            return jsonify({
                'status': 'success',
                'message': 'SMB share configuration created successfully',
                'data': {
                    'action': 'add',
                    'server': server,
                    'share': share,
                    'mountpoint': final_mountpoint,
                    'note': 'Configuration saved. Use /api/v1/smb/mount-all to mount all configured shares.'
                }
            })
        else:
            # Distinguish between different types of errors
            if "already exists" in error_msg:
                return jsonify({
                    'status': 'error',
                    'message': 'Mount configuration already exists',
                    'error': 'configuration_exists',
                    'details': error_msg
                }), 400
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to save mount configuration',
                    'error': 'configuration_save_failed',
                    'details': error_msg
                }), 500
    
    def _handle_remove_mount(self, data: Dict[str, Any], server: str, share: str) -> Dict[str, Any]:
        """Helper method to handle removing a mount configuration"""
        logger.debug(f"Removing SMB mount configuration for {server}/{share}")
        
        # Remove mount configuration (but don't unmount)
        success, mountpoint = remove_mount_config(server, share)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'SMB share configuration removed successfully',
                'data': {
                    'action': 'remove',
                    'server': server,
                    'share': share,
                    'mountpoint': mountpoint,
                    'note': 'Configuration removed. Restart sambamount service to apply changes to active mounts.'
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Mount configuration not found for {server}/{share}',
                'error': 'Configuration not found',
                'details': f'No mount configuration exists for server {server} and share {share}'
            }), 404

    def handle_mount_all_samba(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/mount-all
        Mount all configured Samba shares by triggering the sambamount systemd service.
        Also manages cleanup of shares that are no longer configured.
        """
        try:
            logger.debug("Processing samba mount-all request")
            
            # Load previous mount state
            previous_state = load_mount_state()
            
            # Get current mount configurations
            current_mounts = list_configured_mounts()
            current_state = {}
            
            # Build current state mapping
            for mount in current_mounts:
                mount_key = get_mount_key(mount['server'], mount['share'])
                current_state[mount_key] = mount['mountpoint']
            
            # Find mounts that need to be removed (in previous state but not in current)
            mounts_to_remove = []
            for mount_key, mountpoint in previous_state.items():
                if mount_key not in current_state:
                    mounts_to_remove.append((mount_key, mountpoint))
            
            # Unmount shares that are no longer configured
            unmounted_shares = []
            for mount_key, mountpoint in mounts_to_remove:
                server_share = mount_key  # mount_key is already "server/share"
                logger.info(f"Unmounting removed share: {server_share} at {mountpoint}")
                if unmount_share(mountpoint):
                    unmounted_shares.append({
                        'mount_key': server_share,
                        'mountpoint': mountpoint,
                        'status': 'unmounted'
                    })
                    # Remove from previous state since successfully unmounted
                    del previous_state[mount_key]
                else:
                    # Log warning but continue processing - don't fail the entire operation
                    logger.warning(f"Failed to unmount {server_share} at {mountpoint}, but continuing")
                    unmounted_shares.append({
                        'mount_key': server_share,
                        'mountpoint': mountpoint,
                        'status': 'unmount_failed'
                    })
                    # Keep it in the state since it's still mounted
            
            logger.debug("Restarting sambamount systemd service to mount all Samba shares")
            
            # Restart the sambamount service
            result = subprocess.run(
                ['systemctl', 'restart', 'sambamount.service'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("sambamount.service restarted successfully")
                
                # Save the new state: current configurations + any failed unmounts
                # Start with current configurations
                final_state = current_state.copy()
                
                # Add back any shares that failed to unmount (they're still mounted)
                for mount_key, mountpoint in previous_state.items():
                    if mount_key not in current_state:
                        # This was a share we tried to remove but might have failed to unmount
                        # Check if it's still in the previous_state (wasn't successfully removed)
                        final_state[mount_key] = mountpoint
                
                save_mount_state(final_state)
                
                # Get the current mount configurations to show what should be mounted
                try:
                    mount_list = []
                    for mount in current_mounts:
                        mount_list.append({
                            'server': mount['server'],
                            'share': mount['share'],
                            'mountpoint': mount['mountpoint'],
                            'id': mount.get('id', '?')
                        })
                    
                    response_data = {
                        'service': 'sambamount.service',
                        'action': 'restarted',
                        'configurations': mount_list,
                        'count': len(mount_list),
                        'note': 'Check service logs with: journalctl -u sambamount.service -f'
                    }
                    
                    # Add cleanup information if any shares were unmounted
                    if unmounted_shares:
                        response_data['cleanup'] = {
                            'unmounted_shares': unmounted_shares,
                            'count': len(unmounted_shares)
                        }
                    
                    return jsonify({
                        'status': 'success',
                        'message': 'Samba mount service restarted successfully',
                        'data': response_data
                    })
                except Exception as list_error:
                    logger.warning(f"Service restarted but failed to list configurations: {list_error}")
                    
                    response_data = {
                        'service': 'sambamount.service',
                        'action': 'restarted',
                        'note': 'Check service logs with: journalctl -u sambamount.service -f'
                    }
                    
                    # Add cleanup information if any shares were unmounted
                    if unmounted_shares:
                        response_data['cleanup'] = {
                            'unmounted_shares': unmounted_shares,
                            'count': len(unmounted_shares)
                        }
                    
                    return jsonify({
                        'status': 'success',
                        'message': 'Samba mount service restarted successfully',
                        'data': response_data
                    })
            else:
                stderr_output = result.stderr.strip()
                stdout_output = result.stdout.strip()
                
                logger.error(f"Failed to restart sambamount.service: {stderr_output}")
                logger.error(f"systemctl restart return code: {result.returncode}")
                if stdout_output:
                    logger.error(f"systemctl restart stdout: {stdout_output}")
                
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to restart Samba mount service',
                    'error': 'Service restart failed',
                    'details': stderr_output or f'systemctl returned exit code {result.returncode}',
                    'data': {
                        'service': 'sambamount.service',
                        'action': 'restart_failed',
                        'return_code': result.returncode
                    }
                }), 500
                
        except subprocess.TimeoutExpired:
            error_msg = "Timeout restarting sambamount.service after 30 seconds"
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': 'Timeout restarting Samba mount service',
                'error': 'Service restart timeout',
                'details': error_msg
            }), 500
            
        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error restarting sambamount.service: {e}"
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': 'Failed to restart Samba mount service',
                'error': 'Subprocess error',
                'details': str(e)
            }), 500
            
        except Exception as e:
            logger.error(f"Error restarting sambamount service: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to restart Samba mount service',
                'error': str(e),
                'details': 'An internal server error occurred while starting the service'
            }), 500
