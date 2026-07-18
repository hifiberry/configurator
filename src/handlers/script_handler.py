#!/usr/bin/env python3
"""
Script Handler - API endpoints for script execution and management.

Provides endpoints for listing configured scripts, executing them
synchronously or in background, and retrieving script information.
"""

import json
import logging
import os
import subprocess
import threading
import time
import traceback
from typing import Any, Dict, List, Union, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Response

try:
    from flask import jsonify, request
except ImportError:
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ScriptHandler:  # pylint: disable=too-many-return-statements
    """Handler for script execution API endpoints"""

    def __init__(
        self, config_file: str = "/etc/configserver/configserver.json"
    ) -> None:
        """Initialize the script handler"""
        logger.debug("Initializing ScriptHandler")
        self.config_file: str = config_file
        self.scripts: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load script configuration from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.scripts = config.get('scripts', {})
                    logger.debug("Loaded %d configured scripts", len(self.scripts))
            else:
                logger.warning("Config file %s not found, no scripts available",
                               self.config_file)
                self.scripts = {}
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Error loading script config: %s", e)
            self.scripts = {}

    def handle_list_scripts(self) -> 'Union[Response, tuple[Response, int]]':
        """Handle GET /api/v1/scripts to list all configured scripts"""
        try:
            script_list: List[Dict[str, Any]] = []
            for script_id, script_config in self.scripts.items():
                script_info: Dict[str, Any] = {
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
            })  # type: ignore[return-value]
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error listing scripts: %s", e)
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to list scripts',
                'error': str(e)
            }), 500  # type: ignore[return-value]

    def handle_execute_script(
        self, script_id: str
    ) -> 'Union[Response, tuple[Response, int]]':
        """Handle POST /api/v1/scripts/{script_id}/execute"""
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
                }), 404  # type: ignore[return-value]

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
                }), 500  # type: ignore[return-value]

            if not os.path.exists(script_path):
                return jsonify({
                    'status': 'error',
                    'message': f'Script path does not exist: {script_path}',
                    'error': 'script_path_not_found',
                    'data': {
                        'script_id': script_id,
                        'script_path': script_path
                    }
                }), 404  # type: ignore[return-value]

            if not os.access(script_path, os.X_OK):
                return jsonify({
                    'status': 'error',
                    'message': f'Script is not executable: {script_path}',
                    'error': 'script_not_executable',
                    'data': {
                        'script_id': script_id,
                        'script_path': script_path
                    }
                }), 403  # type: ignore[return-value]

            # Get optional parameters from request body
            try:
                json_data: Dict[str, Any] = cast(
                    Dict[str, Any],
                    request.get_json() or {}  # type: ignore[union-attr]
                    if request else {}
                )
            except (ValueError, OSError):
                # Handle cases where JSON parsing fails
                json_data = {}

            background: bool = json_data.get('background', False)
            timeout: float = json_data.get('timeout', 300)  # Default 5 minutes

            # Validate timeout
            if timeout <= 0:
                timeout = 300
            elif timeout > 3600:  # Max 1 hour
                timeout = 3600

            # Prepare command
            command = [script_path] + script_args

            logger.info("Executing script '%s' (%s): %s",
                        script_id, script_name, ' '.join(command))

            return (self._execute_script_background(script_id, script_name, command)
                    if background
                    else self._execute_script_sync(script_id, script_name,
                                                   command, timeout))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error executing script %s: %s", script_id, e)
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to execute script "{script_id}"',
                'error': str(e)
            }), 500  # type: ignore[return-value]

    def _execute_script_sync(
        self,
        script_id: str,
        script_name: str,
        command: List[str],
        timeout: float
    ) -> 'Union[Response, tuple[Response, int]]':
        """Execute script synchronously and wait for completion"""
        try:
            start_time = time.time()

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )

            execution_time = time.time() - start_time

            logger.info("Script '%s' completed with exit code %d in %.2fs",
                        script_id, result.returncode, execution_time)

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
            })  # type: ignore[return-value]
        except subprocess.TimeoutExpired:
            logger.error("Script '%s' timed out after %f seconds",
                         script_id, timeout)
            return jsonify({
                'status': 'error',
                'message': f'Script "{script_name}" execution timed out',
                'error': 'execution_timeout',
                'data': {
                    'script_id': script_id,
                    'script_name': script_name,
                    'timeout': timeout
                }
            }), 500  # type: ignore[return-value]
        except subprocess.SubprocessError as e:
            logger.error("Subprocess error executing script '%s': %s",
                         script_id, e)
            return jsonify({
                'status': 'error',
                'message': f'Failed to execute script "{script_name}"',
                'error': 'subprocess_error',
                'data': {
                    'script_id': script_id,
                    'script_name': script_name,
                    'system_error': str(e)
                }
            }), 500  # type: ignore[return-value]

    def _execute_script_background(
        self, script_id: str, script_name: str, command: List[str]
    ) -> 'Response':
        """Execute script in background and return immediately"""
        def run_script():
            """Run script in thread"""
            try:
                logger.info("Starting background execution of script '%s'",
                           script_id)
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3600,  # 1 hour max for background scripts
                    check=False
                )
                logger.info("Background script '%s' completed with exit code %d",
                           script_id, result.returncode)
            except subprocess.TimeoutExpired:
                logger.error("Background script '%s' timed out after 3600s",
                            script_id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Background script '%s' failed: %s", script_id, e)

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
                'note': ('Script is running in background. '
                         'Check system logs for completion status.')
            }
        })  # type: ignore[return-value]

    def handle_get_script_info(
        self, script_id: str
    ) -> 'Union[Response, tuple[Response, int]]':
        """Handle GET /api/v1/scripts/{script_id}"""
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
                }), 404  # type: ignore[return-value]

            script_config = self.scripts[script_id]
            script_path = script_config.get('path', '')

            # Check if script file exists and is executable
            path_exists = os.path.exists(script_path) if script_path else False
            path_executable = (os.access(script_path, os.X_OK)
                               if path_exists else False)

            script_info: Dict[str, Any] = {
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
            })  # type: ignore[return-value]
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting script info for %s: %s", script_id, e)
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': f'Failed to get information for script "{script_id}"',
                'error': str(e)
            }), 500  # type: ignore[return-value]
