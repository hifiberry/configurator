#!/usr/bin/env python3

import logging
import re
import subprocess
from flask import jsonify, request
from typing import Dict, Any, Optional, Tuple
import traceback

logger = logging.getLogger(__name__)

class HostnameHandler:
    """Handler for hostname related API endpoints"""
    
    def __init__(self):
        """Initialize the hostname handler"""
        logger.debug("Initializing HostnameHandler")
    
    def _get_hostnames(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get current system hostname and pretty hostname using hostnamectl.
        
        Returns:
            Tuple of (hostname, pretty_hostname) or (None, None) if error
        """
        try:
            # Get hostname
            result = subprocess.run(['hostnamectl', 'hostname'], 
                                  capture_output=True, text=True, timeout=5)
            hostname = result.stdout.strip() if result.returncode == 0 else None
            
            # Get pretty hostname
            result = subprocess.run(['hostnamectl', '--pretty'], 
                                  capture_output=True, text=True, timeout=5)
            pretty_hostname = result.stdout.strip() if result.returncode == 0 else None
            
            # If pretty hostname is empty, it's not set
            if pretty_hostname == "":
                pretty_hostname = None
                
            logger.debug(f"Retrieved hostnames - hostname: {hostname}, pretty: {pretty_hostname}")
            return hostname, pretty_hostname
            
        except Exception as e:
            logger.error(f"Error getting hostnames: {e}")
            return None, None
    
    def _sanitize_hostname(self, pretty_hostname: str) -> str:
        """
        Convert pretty hostname to valid system hostname.
        Rules: max 16 chars, lowercase, ASCII only, no special chars except hyphens
        
        Args:
            pretty_hostname: The pretty hostname to convert
            
        Returns:
            Sanitized hostname suitable for system use
        """
        # Convert to lowercase and replace spaces with hyphens
        hostname = pretty_hostname.lower().replace(' ', '-')
        
        # Keep only ASCII letters, numbers, and hyphens
        hostname = re.sub(r'[^a-z0-9-]', '', hostname)
        
        # Remove leading/trailing hyphens and multiple consecutive hyphens
        hostname = re.sub(r'-+', '-', hostname).strip('-')
        
        # Limit to 16 characters
        hostname = hostname[:16]
        
        # Ensure it doesn't end with a hyphen
        hostname = hostname.rstrip('-')
        
        # If empty or starts with hyphen, use fallback
        if not hostname or hostname.startswith('-'):
            hostname = 'hifiberry'
        
        logger.debug(f"Sanitized '{pretty_hostname}' to '{hostname}'")
        return hostname
    
    def _validate_hostname(self, hostname: str) -> bool:
        """
        Validate system hostname format.
        
        Args:
            hostname: Hostname to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not hostname or len(hostname) > 16:
            return False
        
        # Must be lowercase ASCII letters, numbers, and hyphens only
        if not re.match(r'^[a-z0-9-]+$', hostname):
            return False
        
        # Cannot start or end with hyphen
        if hostname.startswith('-') or hostname.endswith('-'):
            return False
        
        return True
    
    def _validate_pretty_hostname(self, pretty_hostname: str) -> bool:
        """
        Validate pretty hostname format.
        
        Args:
            pretty_hostname: Pretty hostname to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not pretty_hostname:
            return False
        
        # Must be printable ASCII characters and reasonable length
        if len(pretty_hostname) > 64:
            return False
        
        # Check for printable ASCII characters
        try:
            pretty_hostname.encode('ascii')
            if not pretty_hostname.isprintable():
                return False
        except UnicodeEncodeError:
            return False
        
        return True
    
    def _set_hostname(self, hostname: str) -> bool:
        """
        Set system hostname using hostnamectl.
        
        Args:
            hostname: The hostname to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(['hostnamectl', 'set-hostname', hostname], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                logger.info(f"Successfully set hostname to: {hostname}")
                return True
            else:
                logger.error(f"Failed to set hostname: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting hostname: {e}")
            return False
    
    def _set_pretty_hostname(self, pretty_hostname: str) -> bool:
        """
        Set pretty hostname using hostnamectl.
        
        Args:
            pretty_hostname: The pretty hostname to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(['hostnamectl', 'set-hostname', '--pretty', pretty_hostname], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                logger.info(f"Successfully set pretty hostname to: {pretty_hostname}")
                return True
            else:
                logger.error(f"Failed to set pretty hostname: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting pretty hostname: {e}")
            return False
    
    def handle_get_hostname(self) -> Dict[str, Any]:
        """
        Handle GET /api/v1/hostname
        Get current system and pretty hostnames
        """
        try:
            logger.debug("Getting current hostnames")
            
            hostname, pretty_hostname = self._get_hostnames()
            
            if hostname is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to retrieve hostname information'
                }), 500
            
            # If no pretty hostname is set, use the normal hostname
            if pretty_hostname is None:
                pretty_hostname = hostname
            
            return jsonify({
                'status': 'success',
                'data': {
                    'hostname': hostname,
                    'pretty_hostname': pretty_hostname
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting hostname: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to get hostname',
                'error': str(e)
            }), 500
    
    def handle_set_hostname(self) -> Dict[str, Any]:
        """
        Handle POST /api/v1/hostname
        Set system hostname (and optionally pretty hostname)
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
            
            hostname = data.get('hostname')
            pretty_hostname = data.get('pretty_hostname')
            
            # Must provide at least one
            if not hostname and not pretty_hostname:
                return jsonify({
                    'status': 'error',
                    'message': 'Must provide either hostname or pretty_hostname'
                }), 400
            
            # If pretty hostname provided, derive regular hostname from it
            if pretty_hostname:
                if not self._validate_pretty_hostname(pretty_hostname):
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid pretty hostname format'
                    }), 400
                
                # Derive hostname from pretty hostname if not explicitly provided
                if not hostname:
                    hostname = self._sanitize_hostname(pretty_hostname)
            
            # Validate hostname
            if hostname and not self._validate_hostname(hostname):
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid hostname format (max 16 chars, lowercase ASCII, no special chars except hyphens)'
                }), 400
            
            logger.debug(f"Setting hostnames - hostname: {hostname}, pretty: {pretty_hostname}")
            
            # Set the hostnames
            success = True
            
            if hostname:
                if not self._set_hostname(hostname):
                    success = False
            
            if pretty_hostname and success:
                if not self._set_pretty_hostname(pretty_hostname):
                    success = False
            
            if success:
                # Get updated hostnames to return
                new_hostname, new_pretty = self._get_hostnames()
                
                return jsonify({
                    'status': 'success',
                    'message': 'Hostname updated successfully',
                    'data': {
                        'hostname': new_hostname,
                        'pretty_hostname': new_pretty
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to update hostname'
                }), 500
                
        except Exception as e:
            logger.error(f"Error setting hostname: {e}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'status': 'error',
                'message': 'Failed to set hostname',
                'error': str(e)
            }), 500
