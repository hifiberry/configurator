#!/usr/bin/env python3

import logging
import subprocess
import threading
import time
from typing import Dict, Any, Union, cast
import traceback
from flask import jsonify, request, Response

logger = logging.getLogger(__name__)

class SystemHandler:
    """Handler for system operation API endpoints"""
    
    def __init__(self) -> None:
        """Initialize the system handler"""
        logger.debug("Initializing SystemHandler")
    
    def handle_reboot(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/system/reboot
        Reboot the system after a short delay
        """
        try:
            logger.info("System reboot requested via API")
            
            # Parse optional delay parameter
            delay: int = 5  # Default 5 second delay
            
            if request.is_json:
                data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
                if data and 'delay' in data:
                    try:
                        delay = int(data['delay'])
                        if delay < 0 or delay > 300:  # Max 5 minutes
                            return jsonify({
                                'status': 'error',
                                'message': 'Delay must be between 0 and 300 seconds'
                            }), 400
                    except (ValueError, TypeError):
                        return jsonify({
                            'status': 'error',
                            'message': 'Delay must be a valid integer'
                        }), 400
            
            # Schedule reboot in background thread
            def delayed_reboot() -> None:
                try:
                    logger.info(f"Waiting {delay} seconds before reboot...")
                    time.sleep(delay)
                    logger.info("Executing system reboot...")
                    subprocess.run(['/usr/sbin/reboot'], check=True)
                except Exception as e:
                    logger.error(f"Failed to execute reboot: {e}")
            
            # Start background thread for delayed reboot
            reboot_thread: threading.Thread = threading.Thread(target=delayed_reboot, daemon=True)
            reboot_thread.start()
            
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'message': f'System reboot scheduled in {delay} seconds',
                'data': {
                    'delay': delay,
                    'scheduled': True
                }
            })
            
        except Exception as e:
            logger.error(f"Error handling reboot request: {e}")
            logger.error(traceback.format_exc())
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to schedule system reboot',
                'error': str(e)
            }), 500
    
    def handle_shutdown(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/system/shutdown
        Shutdown the system after a short delay
        """
        try:
            logger.info("System shutdown requested via API")
            
            # Parse optional delay parameter
            delay: int = 5  # Default 5 second delay
            
            if request.is_json:
                data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
                if data and 'delay' in data:
                    try:
                        delay = int(data['delay'])
                        if delay < 0 or delay > 300:  # Max 5 minutes
                            return jsonify({
                                'status': 'error',
                                'message': 'Delay must be between 0 and 300 seconds'
                            }), 400
                    except (ValueError, TypeError):
                        return jsonify({
                            'status': 'error',
                            'message': 'Delay must be a valid integer'
                        }), 400
            
            # Schedule shutdown in background thread
            def delayed_shutdown() -> None:
                try:
                    logger.info(f"Waiting {delay} seconds before shutdown...")
                    time.sleep(delay)
                    logger.info("Executing system shutdown...")
                    subprocess.run(['/usr/sbin/shutdown', 'now'], check=True)
                except Exception as e:
                    logger.error(f"Failed to execute shutdown: {e}")
            
            # Start background thread for delayed shutdown
            shutdown_thread: threading.Thread = threading.Thread(target=delayed_shutdown, daemon=True)
            shutdown_thread.start()
            
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'message': f'System shutdown scheduled in {delay} seconds',
                'data': {
                    'delay': delay,
                    'scheduled': True
                }
            })
            
        except Exception as e:
            logger.error(f"Error handling shutdown request: {e}")
            logger.error(traceback.format_exc())
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to schedule system shutdown',
                'error': str(e)
            }), 500
