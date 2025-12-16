#!/usr/bin/env python3
"""
HiFiBerry Configuration API Systemd Handler

Handles systemd service operations with proper access control based on configuration.
"""

import os
import json
import logging
import subprocess
from typing import Dict, Any, Optional, List

try:
    from flask import request, jsonify
except ImportError:
    # Flask not available - likely during testing or installation
    request = None
    jsonify = None

from ..config_parser import get_config_section
from ..systemd_service import SystemdServiceManager

# Set up logging
logger = logging.getLogger(__name__)

class SystemdHandler:
    """Handler for systemd service operations with access control"""
    
    def __init__(self):
        """Initialize the systemd handler"""
        self.allowed_operations = {
            'all': ['start', 'stop', 'restart', 'enable', 'disable', 'enable-now', 'disable-now', 'status'],
            'status': ['status']
        }
        # Initialize the systemd service manager that handles both system and user services
        try:
            self.service_manager = SystemdServiceManager()
            logger.info(f"SystemdServiceManager initialized successfully")
            # Log some debug info about detected services
            if hasattr(self.service_manager, 'service_environments'):
                logger.info(f"Service environment map: {self.service_manager.service_environments}")
            if hasattr(self.service_manager, 'user_name'):
                logger.info(f"Detected user: {self.service_manager.user_name}")
        except Exception as e:
            logger.error(f"Failed to initialize SystemdServiceManager: {e}")
            self.service_manager = None
    
    def _get_service_permissions(self, service: str) -> List[str]:
        """Get allowed operations for a service"""
        systemd_config = get_config_section('systemd', {})
        permission_level = systemd_config.get(service, 'status')
        
        if permission_level not in self.allowed_operations:
            permission_level = 'status'
        
        return self.allowed_operations[permission_level]
    
    def _is_operation_allowed(self, service: str, operation: str) -> bool:
        """Check if an operation is allowed for a service"""
        allowed_ops = self._get_service_permissions(service)
        return operation in allowed_ops
    
    def _service_exists(self, service: str) -> bool:
        """Check if a systemd service exists on the system"""
        try:
            if not self.service_manager:
                logger.error("SystemdServiceManager not available")
                return False
                
            # Check if service is in the environment map (detected at startup)
            env = self.service_manager._get_service_environment(service)
            if env:
                logger.debug(f"Service {service} exists in environment: {env}")
                return True
            
            # Fallback: try to get status to see if service exists
            status_success, status_data = self.service_manager.status(service)
            exists = status_success and isinstance(status_data, dict)
            logger.debug(f"Service {service} exists check (fallback): {exists}")
            return exists
            
        except Exception as e:
            logger.error(f"Error checking if service exists: {e}")
            return False
    
    def _execute_systemctl(self, operation: str, service: str) -> tuple:
        """Execute systemctl command safely using the service manager"""
        try:
            # Use the service manager which handles both system and user services
            if operation == 'start':
                success, message = self.service_manager.start(service)
                return (0 if success else 1), message, ''
            elif operation == 'stop':
                success, message = self.service_manager.stop(service)
                return (0 if success else 1), message, ''
            elif operation == 'restart':
                success, message = self.service_manager.restart(service)
                return (0 if success else 1), message, ''
            elif operation == 'enable':
                success, message = self.service_manager.enable(service)
                return (0 if success else 1), message, ''
            elif operation == 'disable':
                success, message = self.service_manager.disable(service)
                return (0 if success else 1), message, ''
            elif operation == 'enable-now':
                success, message = self.service_manager.enable_now(service)
                return (0 if success else 1), message, ''
            elif operation == 'disable-now':
                success, message = self.service_manager.disable_now(service)
                return (0 if success else 1), message, ''
            elif operation == 'status':
                success, data = self.service_manager.status(service)
                output = ''
                if isinstance(data, dict):
                    output = data.get('status_output', '')
                else:
                    output = str(data)
                return (0 if success else 1), output, ''
            elif operation == 'is-active':
                active = self.service_manager.is_active(service)
                return (0 if active else 1), ('active' if active else 'inactive'), ''
            elif operation == 'is-enabled':
                enabled = self.service_manager.is_enabled(service)
                return (0 if enabled else 1), ('enabled' if enabled else 'disabled'), ''
            else:
                return 1, "", f"Unknown operation: {operation}"
                
        except Exception as e:
            logger.error(f"Error executing systemctl {operation} {service}: {e}")
            return 1, "", str(e)
    
    def handle_systemd_operation(self, service: str, operation: str):
        """Flask handler: Execute systemd operation on a service"""
        try:
            # Validate operation
            valid_operations = ['start', 'stop', 'restart', 'enable', 'disable', 'status']
            if operation not in valid_operations:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid operation: {operation}. Valid operations: {valid_operations}'
                }), 400
            
            # Check if service exists on the system
            if not self._service_exists(service):
                return jsonify({
                    'status': 'error',
                    'message': f'Service "{service}" does not exist on the system'
                }), 404
            
            # Check if operation is allowed for this service
            if not self._is_operation_allowed(service, operation):
                allowed_ops = self._get_service_permissions(service)
                return jsonify({
                    'status': 'error',
                    'message': f'Operation "{operation}" not allowed for service "{service}". Allowed operations: {allowed_ops}'
                }), 403
            
            # Execute the systemctl command
            returncode, stdout, stderr = self._execute_systemctl(operation, service)
            
            if returncode == 0:
                return jsonify({
                    'status': 'success',
                    'message': f'Successfully executed {operation} on {service}',
                    'data': {
                        'service': service,
                        'operation': operation,
                        'output': stdout.strip(),
                        'returncode': returncode
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to execute {operation} on {service}',
                    'data': {
                        'service': service,
                        'operation': operation,
                        'output': stdout.strip(),
                        'error': stderr.strip(),
                        'returncode': returncode
                    }
                }), 500
                
        except Exception as e:
            logger.error(f"Error handling systemd operation {operation} on {service}: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Internal error executing {operation} on {service}'
            }), 500
    
    def handle_systemd_status(self, service: str):
        """Flask handler: Get detailed status of a service"""
        try:
            # Check if service exists on the system
            if not self._service_exists(service):
                return jsonify({
                    'status': 'error',
                    'message': f'Service "{service}" does not exist on the system'
                }), 404

            # Get comprehensive status using the service manager
            status_success, status_data = self.service_manager.status(service)
            is_active = self.service_manager.is_active(service)
            is_enabled = self.service_manager.is_enabled(service)

            return jsonify({
                'status': 'success',
                'data': {
                    'service': service,
                    'active': 'active' if is_active else 'inactive',
                    'enabled': 'enabled' if is_enabled else 'disabled',
                    'environment': status_data.get('environment', 'unknown') if isinstance(status_data, dict) else 'unknown',
                    'status_output': status_data.get('status_output', '').strip() if isinstance(status_data, dict) else '',
                    'status_success': status_data.get('status_available', False) if isinstance(status_data, dict) else False,
                    'allowed_operations': self._get_service_permissions(service)
                }
            })

        except Exception as e:
            logger.error(f"Error getting status for service {service}: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Failed to get status for service {service}'
            }), 500
    
    def handle_service_exists(self, service: str):
        """Flask handler: Check if a service exists on the system"""
        try:
            service_exists = self._service_exists(service)
            
            response_data = {
                'service': service,
                'exists': service_exists
            }
            
            # If service exists, also provide basic info
            if service_exists:
                # Get current status using service manager
                is_active = self.service_manager.is_active(service)
                is_enabled = self.service_manager.is_enabled(service)
                status_success, status_data = self.service_manager.status(service)
                
                response_data.update({
                    'active': 'active' if is_active else 'inactive',
                    'enabled': 'enabled' if is_enabled else 'disabled',
                    'environment': status_data.get('environment', 'unknown') if isinstance(status_data, dict) else 'unknown',
                    'allowed_operations': self._get_service_permissions(service)
                })
            
            return jsonify({
                'status': 'success',
                'data': response_data
            })
            
        except Exception as e:
            logger.error(f"Error checking if service exists: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Failed to check if service {service} exists'
            }), 500

    def handle_list_services(self):
        """Flask handler: List all configured services and their permissions"""
        try:
            systemd_config = get_config_section('systemd', {})
            
            services = []
            for service, permission in systemd_config.items():
                allowed_ops = self.allowed_operations.get(permission, ['status'])
                
                # Check if service exists using service manager
                service_exists = self._service_exists(service)
                
                service_info = {
                    'service': service,
                    'permission_level': permission,
                    'allowed_operations': allowed_ops,
                    'exists': service_exists
                }
                
                # Only get status if service exists
                if service_exists:
                    # Get current status using service manager
                    is_active = self.service_manager.is_active(service)
                    is_enabled = self.service_manager.is_enabled(service)
                    status_success, status_data = self.service_manager.status(service)
                    
                    service_info.update({
                        'active': 'active' if is_active else 'inactive',
                        'enabled': 'enabled' if is_enabled else 'disabled',
                        'environment': status_data.get('environment', 'unknown') if isinstance(status_data, dict) else 'unknown'
                    })
                else:
                    service_info.update({
                        'active': 'not-available',
                        'enabled': 'not-available',
                        'environment': 'unknown'
                    })
                
                services.append(service_info)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'services': services,
                    'count': len(services)
                }
            })
            
        except Exception as e:
            logger.error(f"Error listing services: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to list services'
            }), 500
