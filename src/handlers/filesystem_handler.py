#!/usr/bin/env python3

import logging
import os
import json
from flask import jsonify, request, Response
from typing import Dict, List, Any, Union, cast
import traceback

logger = logging.getLogger(__name__)

class FilesystemHandler:
    """Handler for filesystem related API endpoints"""
    
    def __init__(self, config_file: str = "/etc/configserver/configserver.json") -> None:
        """Initialize the filesystem handler"""
        logger.debug("Initializing FilesystemHandler")
        self.config_file: str = config_file
        self.allowed_symlink_destinations: List[str] = []
        self.allowed_exists_check_destinations: List[str] = ['/etc']
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config: Dict[str, Any] = cast(Dict[str, Any], json.load(f))
                    filesystem_config: Dict[str, Any] = cast(Dict[str, Any], config.get('filesystem', {}))
                    self.allowed_symlink_destinations = cast(List[str], filesystem_config.get('allowed_symlink_destinations', []))
                    self.allowed_exists_check_destinations = cast(List[str], filesystem_config.get('allowed_exists_check_destinations', ['/etc']))
                    logger.debug(f"Loaded allowed symlink destinations: {self.allowed_symlink_destinations}")
                    logger.debug(f"Loaded allowed exists check destinations: {self.allowed_exists_check_destinations}")
            else:
                logger.warning(f"Config file {self.config_file} not found, no symlink destinations allowed")
                self.allowed_symlink_destinations = []
                self.allowed_exists_check_destinations = ['/etc']
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.allowed_symlink_destinations = []
            self.allowed_exists_check_destinations = ['/etc']
    
    def handle_list_symlinks(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/filesystem/symlinks
        List all symlinks in a given directory including their destinations
        """
        try:
            # Get JSON data from request
            if not request.is_json:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Content-Type must be application/json'
                }), 400
            
            data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
            if not data:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Missing request body'
                }), 400
            
            # Validate required fields
            directory: str = cast(str, data.get('directory'))
            if not directory:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Missing required field: directory'
                }), 400
            
            # Check if directory access is allowed
            if not self.allowed_symlink_destinations:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Directory access is not allowed - no destinations configured',
                    'error': 'directory_access_not_allowed'
                }), 403
            
            # Validate directory is in allowed list
            directory_allowed: bool = False
            for allowed_dest in self.allowed_symlink_destinations:
                if directory.startswith(allowed_dest):
                    directory_allowed = True
                    break
            
            if not directory_allowed:
                return jsonify({  # type: ignore[return-value]
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
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Directory does not exist',
                    'data': {
                        'directory': directory
                    }
                }), 404
            
            if not os.path.isdir(directory):
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Path is not a directory',
                    'data': {
                        'directory': directory
                    }
                }), 400
            
            # Get symlinks
            try:
                symlinks: List[Dict[str, Any]] = []
                for item in os.listdir(directory):
                    item_path: str = os.path.join(directory, item)
                    if os.path.islink(item_path):
                        try:
                            # Get symlink target
                            target: str = os.readlink(item_path)
                            
                            # Check if target exists
                            target_exists: bool = os.path.exists(item_path)  # This follows the symlink
                            
                            # Get absolute target path
                            if not os.path.isabs(target):
                                abs_target: str = os.path.abspath(os.path.join(directory, target))
                            else:
                                abs_target = target
                            
                            # Get symlink info
                            try:
                                stat_info = os.lstat(item_path)  # lstat doesn't follow symlinks
                                symlinks.append(cast(Dict[str, Any], {
                                    'name': item,
                                    'path': item_path,
                                    'target': target,
                                    'absolute_target': abs_target,
                                    'target_exists': target_exists,
                                    'modified': stat_info.st_mtime,
                                    'permissions': oct(stat_info.st_mode)[-3:]
                                }))
                            except OSError as e:
                                # Include the symlink but with limited info if we can't stat it
                                symlinks.append(cast(Dict[str, Any], {
                                    'name': item,
                                    'path': item_path,
                                    'target': target,
                                    'absolute_target': abs_target,
                                    'target_exists': target_exists,
                                    'error': f'Cannot access symlink info: {str(e)}'
                                }))
                        except OSError as e:
                            # Include the symlink but with error info if we can't read the target
                            symlinks.append(cast(Dict[str, Any], {
                                'name': item,
                                'path': item_path,
                                'error': f'Cannot read symlink target: {str(e)}'
                            }))
                
                # Sort symlinks by name
                symlinks.sort(key=lambda x: cast(str, x['name']).lower())
                
                return jsonify({  # type: ignore[return-value]
                    'status': 'success',
                    'message': 'Symlinks listed successfully',
                    'data': {
                        'directory': directory,
                        'symlinks': symlinks,
                        'count': len(symlinks)
                    }
                })
                
            except PermissionError:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Permission denied accessing directory',
                    'data': {
                        'directory': directory
                    }
                }), 403
                
        except Exception as e:
            logger.error(f"Error listing symlinks: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to list symlinks',
                'error': str(e)
            }), 500
    
    def handle_file_exists(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/filesystem/file-exists
        Check if a given file or directory exists
        """
        try:
            # Get JSON data from request
            if not request.is_json:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Content-Type must be application/json'
                }), 400
            
            data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
            if not data:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Missing request body'
                }), 400
            
            # Validate required fields
            path: str = cast(str, data.get('path'))
            if not path:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Missing required field: path'
                }), 400
            
            # Check if directory access is allowed
            if not self.allowed_exists_check_destinations:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'File access is not allowed - no destinations configured',
                    'error': 'file_access_not_allowed'
                }), 403
            
            # Validate path is in allowed list
            path_allowed: bool = False
            for allowed_dest in self.allowed_exists_check_destinations:
                if path.startswith(allowed_dest):
                    path_allowed = True
                    break
            
            if not path_allowed:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Path is not in allowed destinations',
                    'error': 'path_not_allowed',
                    'data': {
                        'path': path,
                        'allowed_destinations': self.allowed_exists_check_destinations
                    }
                }), 403
            
            # Check if path exists
            exists: bool = os.path.exists(path)
            
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'message': f"File {'exists' if exists else 'does not exist'}",
                'data': {
                    'exists': exists
                }
            })
            
        except Exception as e:
            logger.error(f"Error checking file existence: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to check file existence',
                'error': str(e)
            }), 500
