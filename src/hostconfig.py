#!/usr/bin/env python3
"""
Host Configuration Module

Handles hostname updates including /etc/hosts file management.
"""

import logging
import re
import subprocess
import os
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)

HOSTS_FILE = "/etc/hosts"


def read_hosts_file() -> List[str]:
    """
    Read the contents of /etc/hosts file.
    
    Returns:
        List of lines from the hosts file
    """
    try:
        with open(HOSTS_FILE, 'r') as f:
            return f.readlines()
    except Exception as e:
        logger.error(f"Error reading {HOSTS_FILE}: {e}")
        return []


def write_hosts_file(lines: List[str]) -> bool:
    """
    Write lines to /etc/hosts file.
    
    Args:
        lines: List of lines to write
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create backup
        backup_file = f"{HOSTS_FILE}.backup"
        with open(HOSTS_FILE, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())
        
        # Write new content
        with open(HOSTS_FILE, 'w') as f:
            f.writelines(lines)
        
        logger.info(f"Successfully updated {HOSTS_FILE}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing {HOSTS_FILE}: {e}")
        return False


def update_hosts_file(old_hostname: Optional[str], new_hostname: str) -> bool:
    """
    Update /etc/hosts file when hostname changes.
    Removes old hostname entries and adds new hostname as 127.0.0.1.
    This function is designed to be resilient - individual failures like
    removing old hostnames won't cause the entire operation to fail.
    
    Args:
        old_hostname: Previous hostname to remove (can be None)
        new_hostname: New hostname to add
        
    Returns:
        True if successful, False only if critical operations fail
    """
    try:
        lines = read_hosts_file()
        if not lines:
            # If file doesn't exist or is empty, create basic structure
            lines = [
                "127.0.0.1\tlocalhost\n",
                "::1\t\tlocalhost ip6-localhost ip6-loopback\n",
                "ff02::1\t\tip6-allnodes\n",
                "ff02::2\t\tip6-allrouters\n"
            ]
        
        updated_lines = []
        hostname_added = False
        
        for line in lines:
            stripped_line = line.strip()
            
            # Skip empty lines and comments
            if not stripped_line or stripped_line.startswith('#'):
                updated_lines.append(line)
                continue
            
            # Parse the line
            parts = stripped_line.split()
            if len(parts) < 2:
                updated_lines.append(line)
                continue
            
            ip = parts[0]
            hostnames = parts[1:]
            
            # Handle 127.0.0.1 entries
            if ip == "127.0.0.1":
                # Remove old hostname if it exists (non-critical operation)
                if old_hostname and old_hostname in hostnames:
                    try:
                        hostnames = [h for h in hostnames if h != old_hostname]
                        logger.debug(f"Removed old hostname '{old_hostname}' from 127.0.0.1 entry")
                    except Exception as e:
                        logger.warning(f"Failed to remove old hostname '{old_hostname}' from 127.0.0.1 entry: {e}")
                        # Continue anyway - this is not critical
                
                # Add new hostname if not already present and this is localhost entry (critical operation)
                if new_hostname not in hostnames and "localhost" in hostnames:
                    hostnames.append(new_hostname)
                    hostname_added = True
                    logger.debug(f"Added new hostname '{new_hostname}' to 127.0.0.1 entry")
                
                # Reconstruct the line if there are still hostnames
                if hostnames:
                    updated_lines.append(f"{ip}\t{' '.join(hostnames)}\n")
            else:
                # For other IP addresses, just remove old hostname if present (non-critical)
                if old_hostname and old_hostname in hostnames:
                    try:
                        hostnames = [h for h in hostnames if h != old_hostname]
                        logger.debug(f"Removed old hostname '{old_hostname}' from {ip} entry")
                    except Exception as e:
                        logger.warning(f"Failed to remove old hostname '{old_hostname}' from {ip} entry: {e}")
                        # Continue anyway - this is not critical
                
                # Reconstruct the line if there are still hostnames
                if hostnames:
                    updated_lines.append(f"{ip}\t{' '.join(hostnames)}\n")
        
        # If hostname wasn't added to existing 127.0.0.1 entry, create one
        if not hostname_added:
            try:
                # Check if there's already a 127.0.0.1 localhost entry
                has_localhost = any("127.0.0.1" in line and "localhost" in line for line in updated_lines)
                
                if has_localhost:
                    # Find and update the localhost entry
                    for i, line in enumerate(updated_lines):
                        if "127.0.0.1" in line and "localhost" in line:
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                hostnames = parts[1:]
                                if new_hostname not in hostnames:
                                    hostnames.append(new_hostname)
                                    updated_lines[i] = f"127.0.0.1\t{' '.join(hostnames)}\n"
                                    logger.debug(f"Added new hostname '{new_hostname}' to existing localhost entry")
                                    hostname_added = True
                            break
                else:
                    # Add new 127.0.0.1 entry
                    updated_lines.insert(0, f"127.0.0.1\tlocalhost {new_hostname}\n")
                    logger.debug(f"Created new 127.0.0.1 entry with hostname '{new_hostname}'")
                    hostname_added = True
            except Exception as e:
                logger.warning(f"Failed to add new hostname to hosts file: {e}")
                # This is more critical, but we'll still try to write the file
        
        # Always attempt to write the file, even if hostname addition failed
        write_success = write_hosts_file(updated_lines)
        
        if not write_success:
            logger.error("Failed to write updated hosts file")
            return False
            
        if hostname_added:
            logger.info(f"Successfully updated /etc/hosts with new hostname '{new_hostname}'")
        else:
            logger.warning(f"Could not add hostname '{new_hostname}' to /etc/hosts, but file was updated")
            
        return True
        
    except Exception as e:
        logger.error(f"Error updating hosts file: {e}")
        return False


def get_current_hostname() -> Optional[str]:
    """
    Get current system hostname using hostnamectl.
    
    Returns:
        Current hostname or None if error
    """
    try:
        result = subprocess.run(['hostnamectl', 'hostname'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            hostname = result.stdout.strip()
            logger.debug(f"Current hostname: {hostname}")
            return hostname
        else:
            logger.error(f"Failed to get hostname: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error getting hostname: {e}")
        return None


def set_hostname_with_hosts_update(new_hostname: str) -> bool:
    """
    Set system hostname and update /etc/hosts file.
    
    Args:
        new_hostname: The hostname to set
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current hostname before changing
        old_hostname = get_current_hostname()
        
        # Set the new hostname using hostnamectl
        result = subprocess.run(['hostnamectl', 'set-hostname', new_hostname], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            logger.error(f"Failed to set hostname: {result.stderr}")
            return False
        
        logger.info(f"Successfully set hostname from '{old_hostname}' to '{new_hostname}'")
        
        # Update /etc/hosts file
        if not update_hosts_file(old_hostname, new_hostname):
            logger.warning("Failed to update /etc/hosts file, but hostname was set successfully")
            # Don't return False here as the hostname was set successfully
        
        return True
        
    except Exception as e:
        logger.error(f"Error setting hostname with hosts update: {e}")
        return False


def validate_hostname(hostname: str) -> bool:
    """
    Validate system hostname format.
    RFC 1123 compliant: up to 64 chars, ASCII letters/numbers/hyphens, no leading/trailing hyphens
    
    Args:
        hostname: Hostname to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not hostname or len(hostname) > 64:
        return False
    
    # Must be ASCII letters, numbers, and hyphens only
    if not re.match(r'^[a-zA-Z0-9-]+$', hostname):
        return False
    
    # Cannot start or end with hyphen
    if hostname.startswith('-') or hostname.endswith('-'):
        return False
    
    # Each label (part separated by dots) must be <= 63 chars
    labels = hostname.split('.')
    for label in labels:
        if len(label) > 63 or len(label) == 0:
            return False
        if label.startswith('-') or label.endswith('-'):
            return False
    
    return True


def sanitize_hostname(pretty_hostname: str, max_length: int = 64) -> str:
    """
    Convert pretty hostname to valid system hostname.
    
    Args:
        pretty_hostname: The pretty hostname to convert
        max_length: Maximum length for the hostname (default 64)
        
    Returns:
        Sanitized hostname suitable for system use
    """
    # Convert to lowercase and replace spaces with hyphens
    hostname = pretty_hostname.lower().replace(' ', '-')
    
    # Keep only ASCII letters, numbers, and hyphens
    hostname = re.sub(r'[^a-z0-9-]', '', hostname)
    
    # Remove leading/trailing hyphens and multiple consecutive hyphens
    hostname = re.sub(r'-+', '-', hostname).strip('-')
    
    # Limit to max_length characters
    hostname = hostname[:max_length]
    
    # Ensure it doesn't end with a hyphen
    hostname = hostname.rstrip('-')
    
    # If empty or starts with hyphen, use fallback
    if not hostname or hostname.startswith('-'):
        hostname = 'hifiberry'
    
    logger.debug(f"Sanitized '{pretty_hostname}' to '{hostname}'")
    return hostname
