#!/usr/bin/env python3

import logging
import os
import json
import subprocess
from flask import jsonify, request
from typing import Dict, List, Any, Optional
import traceback

logger = logging.getLogger(__name__)

class FilesystemHandler:
    """Handler for filesystem related API endpoints"""
    
    def __init__(self, config_file="/etc/configserver/configserver.json"):
        """Initialize the filesystem handler"""
        logger.debug("Initializing FilesystemHandler")
        self.config_file = config_file
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    filesystem_config = config.get('filesystem', {})
                    self.allowed_symlink_destinations = filesystem_config.get('allowed_symlink_destinations', [])
                    logger.debug(f"Loaded allowed symlink destinations: {self.allowed_symlink_destinations}")
            else:
                logger.warning(f"Config file {self.config_file} not found, no symlink destinations allowed")
                self.allowed_symlink_destinations = []
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.allowed_symlink_destinations = []
    
    def handle_list_symlinks(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/filesystem/symlinks
        List all symlinks in a given directory including their destinations
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
            directory = data.get('directory')
            if not directory:
                return jsonify({
                    'status': 'error',
                    'message': 'Missing required field: directory'
                }), 400
            
            # Check if directory access is allowed
            if not self.allowed_symlink_destinations:
                return jsonify({
                    'status': 'error',
                    'message': 'Directory access is not allowed - no destinations configured',
                    'error': 'directory_access_not_allowed'
                }), 403
            
            # Validate directory is in allowed list
            directory_allowed = False
            for allowed_dest in self.allowed_symlink_destinations:
                if directory.startswith(allowed_dest):
                    directory_allowed = True
                    break
            
            if not directory_allowed:
                return jsonify({
                    'status': 'error',
                    'message': 'Directory is not in allowed destinations',
                    'error': 'directory_not_allowed',
                    'data': {
                        'directory': directory,
                        'allowed_destinations': self.allowed_symlink_destinations
                    }
                }), 403
            
            # Validate path exists and is a directory
            if not os.path.exists(directory):
                return jsonify({
                    'status': 'error',
                    'message': 'Directory does not exist',
                    'data': {
                        'directory': directory
                    }
                }), 404
            
            if not os.path.isdir(directory):
                return jsonify({
                    'status': 'error',
                    'message': 'Path is not a directory',
                    'data': {
                        'directory': directory
                    }
                }), 400
            
            # Get symlinks
            try:
                symlinks = []
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    if os.path.islink(item_path):
                        try:
                            # Get symlink target
                            target = os.readlink(item_path)
                            
                            # Check if target exists
                            target_exists = os.path.exists(item_path)  # This follows the symlink
                            
                            # Get absolute target path
                            if not os.path.isabs(target):
                                abs_target = os.path.abspath(os.path.join(directory, target))
                            else:
                                abs_target = target
                            
                            # Get symlink info
                            try:
                                stat_info = os.lstat(item_path)  # lstat doesn't follow symlinks
                                symlinks.append({
                                    'name': item,
                                    'path': item_path,
                                    'target': target,
                                    'absolute_target': abs_target,
                                    'target_exists': target_exists,
                                    'modified': stat_info.st_mtime,
                                    'permissions': oct(stat_info.st_mode)[-3:]
                                })
                            except OSError as e:
                                # Include the symlink but with limited info if we can't stat it
                                symlinks.append({
                                    'name': item,
                                    'path': item_path,
                                    'target': target,
                                    'absolute_target': abs_target,
                                    'target_exists': target_exists,
                                    'error': f'Cannot access symlink info: {str(e)}'
                                })
                        except OSError as e:
                            # Include the symlink but with error info if we can't read the target
                            symlinks.append({
                                'name': item,
                                'path': item_path,
                                'error': f'Cannot read symlink target: {str(e)}'
                            })
                
                # Sort symlinks by name
                symlinks.sort(key=lambda x: x['name'].lower())
                
                return jsonify({
                    'status': 'success',
                    'message': 'Symlinks listed successfully',
                    'data': {
                        'directory': directory,
                        'symlinks': symlinks,
                        'count': len(symlinks)
                    }
                })
                
            except PermissionError:
                return jsonify({
                    'status': 'error',
                    'message': 'Permission denied accessing directory',
                    'data': {
                        'directory': directory
                    }
                }), 403
                
        except Exception as e:
            logger.error(f"Error listing symlinks: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to list symlinks',
                'error': str(e)
            }), 500
