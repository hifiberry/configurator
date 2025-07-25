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

# Set up logging
logger = logging.getLogger(__name__)

class SystemdHandler:
    """Handler for systemd service operations with access control"""
    
    def __init__(self):
        """Initialize the systemd handler"""
        self.allowed_operations = {
            'all': ['start', 'stop', 'restart', 'enable', 'disable', 'status'],
            'status': ['status']
        }
    
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
            # Use systemctl cat to check if service exists
            # This works with or without .service suffix
            result = subprocess.run(
                ['systemctl', 'cat', service],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # If service exists, systemctl cat will return 0
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error checking if service exists: {e}")
            return False
    
    def _execute_systemctl(self, operation: str, service: str) -> tuple:
        """Execute systemctl command safely"""
        try:
            # Build the command
            cmd = ['systemctl', operation, service]
            
            # Execute the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout executing systemctl {operation} {service}")
            return 1, "", "Command timed out"
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
            
            # Status is always allowed
            returncode, stdout, stderr = self._execute_systemctl('status', service)
            
            # Also get is-active and is-enabled status
            active_code, active_output, _ = self._execute_systemctl('is-active', service)
            enabled_code, enabled_output, _ = self._execute_systemctl('is-enabled', service)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'service': service,
                    'active': active_output.strip(),
                    'enabled': enabled_output.strip(),
                    'status_output': stdout.strip(),
                    'status_returncode': returncode,
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
                # Get current status
                active_code, active_output, _ = self._execute_systemctl('is-active', service)
                enabled_code, enabled_output, _ = self._execute_systemctl('is-enabled', service)
                
                response_data.update({
                    'active': active_output.strip(),
                    'enabled': enabled_output.strip(),
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
                
                # Check if service exists
                service_exists = self._service_exists(service)
                
                service_info = {
                    'service': service,
                    'permission_level': permission,
                    'allowed_operations': allowed_ops,
                    'exists': service_exists
                }
                
                # Only get status if service exists
                if service_exists:
                    # Get current status
                    active_code, active_output, _ = self._execute_systemctl('is-active', service)
                    enabled_code, enabled_output, _ = self._execute_systemctl('is-enabled', service)
                    
                    service_info.update({
                        'active': active_output.strip(),
                        'enabled': enabled_output.strip()
                    })
                else:
                    service_info.update({
                        'active': 'not-available',
                        'enabled': 'not-available'
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
