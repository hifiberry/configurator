#!/usr/bin/env python3
"""
Hostname Utilities

Core hostname functionality that can be used by both CLI tools and API handlers.
"""

import logging
import re
import subprocess
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def get_hostnames() -> Tuple[Optional[str], Optional[str]]:
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


def sanitize_hostname(pretty_hostname: str) -> str:
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


def validate_hostname(hostname: str) -> bool:
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


def validate_pretty_hostname(pretty_hostname: str) -> bool:
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


def set_hostname(hostname: str) -> bool:
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


def set_pretty_hostname(pretty_hostname: str) -> bool:
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


def get_hostnames_with_fallback() -> Tuple[Optional[str], Optional[str]]:
    """
    Get hostnames with fallback logic: if no pretty hostname is set, use the normal hostname.
    
    Returns:
        Tuple of (hostname, pretty_hostname) where pretty_hostname falls back to hostname if not set
    """
    hostname, pretty_hostname = get_hostnames()
    
    # If no pretty hostname is set, use the normal hostname
    if pretty_hostname is None:
        pretty_hostname = hostname
        
    return hostname, pretty_hostname
