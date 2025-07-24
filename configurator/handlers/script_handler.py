#!/usr/bin/env python3

import logging
import os
import json
import subprocess
import threading
import time
from flask import jsonify, request
from typing import Dict, List, Any, Optional
import traceback

logger = logging.getLogger(__name__)

class ScriptHandler:
    """Handler for script execution API endpoints"""
    
    def __init__(self, config_file="/etc/configserver/configserver.json"):
        """Initialize the script handler"""
        logger.debug("Initializing ScriptHandler")
        self.config_file = config_file
        self._load_config()
    
    def _load_config(self) -> None:
        """Load script configuration from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.scripts = config.get('scripts', {})
                    logger.debug(f"Loaded {len(self.scripts)} configured scripts")
            else:
                logger.warning(f"Config file {self.config_file} not found, no scripts available")
                self.scripts = {}
        except Exception as e:
            logger.error(f"Error loading script config: {e}")
            self.scripts = {}
    
    def handle_list_scripts(self) -> Dict[str, Any]:
        """
        Handle GET /api/v1/scripts
        List all configured scripts
        """
        try:
            script_list = []
            for script_id, script_config in self.scripts.items():
                script_info = {
                    'id': script_id,
                    'name': script_config.get('name', script_id),
                    'description': script_config.get('description', ''),
                    'path': script_config.get('path', ''),
                    'args': script_config.get('args', [])
                }
                script_list.append(script_info)
            
            return jsonify({
                'status': 'success',
                'message': 'Scripts listed successfully',
                'data': {
                    'scripts': script_list,
                    'count': len(script_list)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing scripts: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to list scripts',
                'error': str(e)
            }), 500
    
    def handle_execute_script(self, script_id: str) -> Dict[str, Any]:
        """
        Handle POST /api/v1/scripts/{script_id}/execute
        Execute a configured script
        """
        try:
            # Check if script exists in configuration
            if script_id not in self.scripts:
                return jsonify({
                    'status': 'error',
                    'message': f'Script "{script_id}" not found in configuration',
                    'error': 'script_not_found',
                    'data': {
                        'script_id': script_id,
                        'available_scripts': list(self.scripts.keys())
                    }
                }), 404
            
            script_config = self.scripts[script_id]
            script_path = script_config.get('path')
            script_args = script_config.get('args', [])
            script_name = script_config.get('name', script_id)
            
            # Validate script path exists
            if not script_path:
                return jsonify({
                    'status': 'error',
                    'message': f'Script "{script_id}" has no path configured',
                    'error': 'script_path_missing'
                }), 500
            
            if not os.path.exists(script_path):
                return jsonify({
                    'status': 'error',
                    'message': f'Script path does not exist: {script_path}',
                    'error': 'script_path_not_found',
                    'data': {
                        'script_id': script_id,
                        'script_path': script_path
                    }
                }), 404
            
            if not os.access(script_path, os.X_OK):
                return jsonify({
                    'status': 'error',
                    'message': f'Script is not executable: {script_path}',
                    'error': 'script_not_executable',
                    'data': {
                        'script_id': script_id,
                        'script_path': script_path
                    }
                }), 403
            
            # Get optional parameters from request body
            try:
                data = request.get_json() or {}
            except Exception:
                # Handle cases where JSON parsing fails (empty body, invalid JSON, etc.)
                data = {}
            background = data.get('background', False)
            timeout = data.get('timeout', 300)  # Default 5 minutes
            
            # Validate timeout
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                timeout = 300
            elif timeout > 3600:  # Max 1 hour
                timeout = 3600
            
            # Prepare command
            command = [script_path] + script_args
            
            logger.info(f"Executing script '{script_id}' ({script_name}): {' '.join(command)}")
            
            if background:
                # Execute in background
                return self._execute_script_background(script_id, script_name, command)
            else:
                # Execute synchronously
                return self._execute_script_sync(script_id, script_name, command, timeout)
                
        except Exception as e:
            logger.error(f"Error executing script {script_id}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to execute script "{script_id}"',
                'error': str(e)
            }), 500
    
    def _execute_script_sync(self, script_id: str, script_name: str, command: List[str], timeout: float) -> Dict[str, Any]:
        """Execute script synchronously and wait for completion"""
        try:
            start_time = time.time()
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            
            logger.info(f"Script '{script_id}' completed with exit code {result.returncode} in {execution_time:.2f}s")
            
            return jsonify({
                'status': 'success',
                'message': f'Script "{script_name}" executed successfully',
                'data': {
                    'script_id': script_id,
                    'script_name': script_name,
                    'command': ' '.join(command),
                    'exit_code': result.returncode,
                    'execution_time': round(execution_time, 2),
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'success': result.returncode == 0
                }
            })
            
        except subprocess.TimeoutExpired:
            error_msg = f"Script '{script_id}' timed out after {timeout} seconds"
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': f'Script "{script_name}" execution timed out',
                'error': 'execution_timeout',
                'data': {
                    'script_id': script_id,
                    'script_name': script_name,
                    'timeout': timeout
                }
            }), 500
            
        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error executing script '{script_id}': {e}"
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': f'Failed to execute script "{script_name}"',
                'error': 'subprocess_error',
                'data': {
                    'script_id': script_id,
                    'script_name': script_name,
                    'system_error': str(e)
                }
            }), 500
    
    def _execute_script_background(self, script_id: str, script_name: str, command: List[str]) -> Dict[str, Any]:
        """Execute script in background and return immediately"""
        def run_script():
            try:
                logger.info(f"Starting background execution of script '{script_id}'")
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour max for background scripts
                )
                logger.info(f"Background script '{script_id}' completed with exit code {result.returncode}")
            except Exception as e:
                logger.error(f"Background script '{script_id}' failed: {e}")
        
        # Start script in background thread
        thread = threading.Thread(target=run_script, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'Script "{script_name}" started in background',
            'data': {
                'script_id': script_id,
                'script_name': script_name,
                'command': ' '.join(command),
                'execution_mode': 'background',
                'note': 'Script is running in background. Check system logs for completion status.'
            }
        })
    
    def handle_get_script_info(self, script_id: str) -> Dict[str, Any]:
        """
        Handle GET /api/v1/scripts/{script_id}
        Get information about a specific script
        """
        try:
            if script_id not in self.scripts:
                return jsonify({
                    'status': 'error',
                    'message': f'Script "{script_id}" not found in configuration',
                    'error': 'script_not_found',
                    'data': {
                        'script_id': script_id,
                        'available_scripts': list(self.scripts.keys())
                    }
                }), 404
            
            script_config = self.scripts[script_id]
            script_path = script_config.get('path', '')
            
            # Check if script file exists and is executable
            path_exists = os.path.exists(script_path) if script_path else False
            path_executable = os.access(script_path, os.X_OK) if path_exists else False
            
            script_info = {
                'id': script_id,
                'name': script_config.get('name', script_id),
                'description': script_config.get('description', ''),
                'path': script_path,
                'args': script_config.get('args', []),
                'path_exists': path_exists,
                'path_executable': path_executable,
                'ready': path_exists and path_executable
            }
            
            return jsonify({
                'status': 'success',
                'message': 'Script information retrieved successfully',
                'data': script_info
            })
            
        except Exception as e:
            logger.error(f"Error getting script info for {script_id}: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to get information for script "{script_id}"',
                'error': str(e)
            }), 500
