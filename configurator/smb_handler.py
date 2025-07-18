#!/usr/bin/env python3

import logging
from flask import jsonify, request
from typing import Dict, List, Any, Optional, Tuple
import traceback

from configurator.sambaclient import (
    list_all_servers, 
    check_smb_connection, 
    list_smb_shares
)
from configurator.sambamount import (
    read_mount_config,
    write_mount_config,
    add_mount_config,
    remove_mount_config,
    is_mounted,
    mount_smb_share_by_id,
    unmount_smb_share_by_id,
    find_mount_by_id,
    list_configured_mounts
)

logger = logging.getLogger(__name__)

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
        Handle GET /api/v1/smb/test/<server>
        Test connection to an SMB server
        """
        try:
            # Get optional authentication from query parameters
            username = request.args.get('username')
            password = request.args.get('password')
            
            logger.debug(f"Testing connection to SMB server: {server}")
            
            # Test connection
            connected = check_smb_connection(
                server=server,
                username=username,
                password=password
            )
            
            if connected:
                return jsonify({
                    'status': 'success',
                    'data': {
                        'server': server,
                        'connected': True,
                        'message': 'Connection successful'
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Connection failed',
                    'data': {
                        'server': server,
                        'connected': False,
                        'error': 'Authentication failed or server unreachable'
                    }
                }), 400
                
        except Exception as e:
            logger.error(f"Error testing connection to {server}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Connection failed',
                'data': {
                    'server': server,
                    'connected': False,
                    'error': str(e)
                }
            }), 500
    
    def handle_list_shares(self, server: str) -> Dict[str, Any]:
        """
        Handle GET /api/v1/smb/shares/<server>
        List shares on an SMB server
        """
        try:
            # Get optional authentication from query parameters
            username = request.args.get('username')
            password = request.args.get('password')
            detailed = request.args.get('detailed', 'false').lower() == 'true'
            
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
            logger.error(f"Error listing shares on {server}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to list shares on {server}',
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
    
    def handle_create_mount(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/mount
        Create and mount a new SMB share
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
            
            # Validate required fields
            server = data.get('server')
            share = data.get('share')
            
            if not server or not share:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required fields: server and share'
                }), 400
            
            # Get optional fields
            mountpoint = data.get('mountpoint')
            user = data.get('user')
            password = data.get('password')
            version = data.get('version')
            options = data.get('options')
            
            logger.debug(f"Creating SMB mount for {server}/{share}")
            
            # Add mount configuration
            success = add_mount_config(
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
                    'message': 'SMB share mounted successfully',
                    'data': {
                        'server': server,
                        'share': share,
                        'mountpoint': final_mountpoint,
                        'mounted': True
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to mount SMB share',
                    'error': f'Mount configuration for {server}/{share} already exists or mount failed'
                }), 400
                
        except Exception as e:
            logger.error(f"Error creating SMB mount: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to mount SMB share',
                'error': str(e)
            }), 500
    
    def handle_remove_mount(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/unmount
        Unmount and remove an SMB share configuration
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
            
            # Validate required fields
            server = data.get('server')
            share = data.get('share')
            
            if not server or not share:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required fields: server and share'
                }), 400
            
            logger.debug(f"Removing SMB mount for {server}/{share}")
            
            # Remove mount configuration
            success, mountpoint = remove_mount_config(server, share)
            
            if success:
                return jsonify({
                    'status': 'success',
                    'message': 'SMB share unmounted successfully',
                    'data': {
                        'server': server,
                        'share': share,
                        'mountpoint': mountpoint,
                        'unmounted': True
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Mount configuration not found for {server}/{share}'
                }), 404
                
        except Exception as e:
            logger.error(f"Error removing SMB mount: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to unmount SMB share',
                'error': str(e)
            }), 500

    def handle_mount_by_id(self, mount_id: int) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/mounts/<mount_id>/mount
        Mount an SMB share by its configuration ID
        """
        try:
            logger.debug(f"Mounting SMB share by ID: {mount_id}")
            
            # Find the mount configuration
            mount_config = find_mount_by_id(mount_id)
            if not mount_config:
                return jsonify({
                    'status': 'error',
                    'message': f'Mount configuration with ID {mount_id} not found'
                }), 404
            
            # Mount the share
            success, error_msg = mount_smb_share_by_id(mount_id)
            
            if success:
                return jsonify({
                    'status': 'success',
                    'message': 'SMB share mounted successfully',
                    'data': {
                        'id': mount_id,
                        'server': mount_config['server'],
                        'share': mount_config['share'],
                        'mountpoint': mount_config['mountpoint'],
                        'mounted': True
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': error_msg or f'Failed to mount SMB share with ID {mount_id}',
                    'data': {
                        'id': mount_id,
                        'server': mount_config['server'],
                        'share': mount_config['share'],
                        'mountpoint': mount_config['mountpoint'],
                        'mounted': False
                    }
                }), 500
                
        except Exception as e:
            logger.error(f"Error mounting SMB share by ID: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to mount SMB share',
                'error': str(e)
            }), 500

    def handle_unmount_by_id(self, mount_id: int) -> Dict[str, Any]:
        """
        Handle POST /api/v1/smb/mounts/unmount/<mount_id>
        Unmount an SMB share by its configuration ID
        """
        try:
            logger.debug(f"Unmounting SMB share by ID: {mount_id}")
            
            # Find the mount configuration
            mount_config = find_mount_by_id(mount_id)
            if not mount_config:
                return jsonify({
                    'status': 'error',
                    'message': f'Mount configuration with ID {mount_id} not found'
                }), 404
            
            # Unmount the share
            success, error_msg = unmount_smb_share_by_id(mount_id)
            
            if success:
                return jsonify({
                    'status': 'success',
                    'message': 'SMB share unmounted successfully',
                    'data': {
                        'id': mount_id,
                        'server': mount_config['server'],
                        'share': mount_config['share'],
                        'mountpoint': mount_config['mountpoint'],
                        'mounted': False
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': error_msg or f'Failed to unmount SMB share with ID {mount_id}',
                    'data': {
                        'id': mount_id,
                        'server': mount_config['server'],
                        'share': mount_config['share'],
                        'mountpoint': mount_config['mountpoint'],
                        'mounted': True
                    }
                }), 500
                
        except Exception as e:
            logger.error(f"Error unmounting SMB share by ID: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to unmount SMB share',
                'error': str(e)
            }), 500
