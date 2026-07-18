#!/usr/bin/env python3
"""
Host Configuration Module

Handles system hostname management including hostname validation, sanitization,
and /etc/hosts file management for proper system hostname configuration.
Provides functions for getting/setting hostnames, validating hostname format,
and updating the hosts file when hostname changes.
"""

import argparse
import logging
import re
import subprocess
import sys
from typing import Optional, List

logger = logging.getLogger(__name__)

HOSTS_FILE = "/etc/hosts"


def read_hosts_file() -> List[str]:
    """
    Read the contents of /etc/hosts file.

    Returns:
        List of lines from the hosts file
    """
    try:
        with open(HOSTS_FILE, 'r', encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        logger.error("Error reading %s: %s", HOSTS_FILE, e)
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
        with open(HOSTS_FILE, 'r', encoding='utf-8') as src:
            with open(backup_file, 'w', encoding='utf-8') as dst:
                dst.write(src.read())

        # Write new content
        with open(HOSTS_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        logger.info("Successfully updated %s", HOSTS_FILE)
        return True

    except Exception as e:
        logger.error("Error writing %s: %s", HOSTS_FILE, e)
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

        updated_lines: List[str] = []
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
                        logger.debug("Removed old hostname '%s' from 127.0.0.1 entry", old_hostname)
                    except Exception as e:
                        logger.warning("Failed to remove old hostname '%s' from 127.0.0.1 entry: %s", old_hostname, e)
                        # Continue anyway - this is not critical

                # Add new hostname if not already present and this is localhost entry (critical operation)
                if new_hostname not in hostnames and "localhost" in hostnames:
                    hostnames.append(new_hostname)
                    hostname_added = True
                    logger.debug("Added new hostname '%s' to 127.0.0.1 entry", new_hostname)

                # Reconstruct the line if there are still hostnames
                if hostnames:
                    updated_lines.append(f"{ip}\t{' '.join(hostnames)}\n")
            else:
                # For other IP addresses, just remove old hostname if present (non-critical)
                if old_hostname and old_hostname in hostnames:
                    try:
                        hostnames = [h for h in hostnames if h != old_hostname]
                        logger.debug("Removed old hostname '%s' from %s entry", old_hostname, ip)
                    except Exception as e:
                        logger.warning("Failed to remove old hostname '%s' from %s entry: %s", old_hostname, ip, e)
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
                                    logger.debug("Added new hostname '%s' to existing localhost entry", new_hostname)
                                    hostname_added = True
                            break
                else:
                    # Add new 127.0.0.1 entry
                    updated_lines.insert(0, f"127.0.0.1\tlocalhost {new_hostname}\n")
                    logger.debug("Created new 127.0.0.1 entry with hostname '%s'", new_hostname)
                    hostname_added = True
            except Exception as e:
                logger.warning("Failed to add new hostname to hosts file: %s", e)
                # This is more critical, but we'll still try to write the file

        # Always attempt to write the file, even if hostname addition failed
        write_success = write_hosts_file(updated_lines)

        if not write_success:
            logger.error("Failed to write updated hosts file")
            return False

        if hostname_added:
            logger.info("Successfully updated /etc/hosts with new hostname '%s'", new_hostname)
        else:
            logger.warning("Could not add hostname '%s' to /etc/hosts, but file was updated", new_hostname)

        return True

    except Exception as e:
        logger.error("Error updating hosts file: %s", e)
        return False


def get_current_hostname() -> Optional[str]:
    """
    Get current system hostname using hostnamectl command.

    Executes the 'hostnamectl hostname' command to retrieve the current
    system hostname. Handles errors gracefully and logs appropriately.

    Returns:
        Current hostname string if successful, None if error occurs

    Raises:
        No exceptions raised; errors are logged
    """
    try:
        result = subprocess.run(['hostnamectl', 'hostname'],
                              capture_output=True, text=True, timeout=5, check=False)
        if result.returncode == 0:
            hostname = result.stdout.strip()
            logger.debug("Current hostname: %s", hostname)
            return hostname
        logger.error("Failed to get hostname: %s", result.stderr)
        return None
    except Exception as e:
        logger.error("Error getting hostname: %s", e)
        return None


def set_hostname_with_hosts_update(new_hostname: str) -> bool:
    """
    Set system hostname and update /etc/hosts file accordingly.

    Sets the new hostname using hostnamectl and updates the /etc/hosts file
    to include the new hostname in the 127.0.0.1 entry. Handles the old hostname
    cleanup and ensures system consistency.

    Args:
        new_hostname: The new hostname to set for the system

    Returns:
        True if hostname was set successfully (hosts file update is secondary),
        False if setting hostname failed

    Note:
        Failures to update /etc/hosts will not cause this to return False,
        as the hostname change is the critical operation.
    """
    try:
        # Get current hostname before changing
        old_hostname = get_current_hostname()

        # Set the new hostname using hostnamectl
        result = subprocess.run(['hostnamectl', 'set-hostname', new_hostname],
                              capture_output=True, text=True, timeout=10, check=False)

        if result.returncode != 0:
            logger.error("Failed to set hostname: %s", result.stderr)
            return False

        logger.info("Successfully set hostname from '%s' to '%s'", old_hostname, new_hostname)

        # Update /etc/hosts file
        if not update_hosts_file(old_hostname, new_hostname):
            logger.warning("Failed to update /etc/hosts file, but hostname was set successfully")
            # Don't return False here as the hostname was set successfully

        return True

    except Exception as e:
        logger.error("Error setting hostname with hosts update: %s", e)
        return False


def validate_hostname(hostname: str) -> bool:
    """
    Validate system hostname format according to RFC 1123 standards.

    Validates that a hostname follows RFC 1123 requirements:
    - Maximum 64 characters total
    - Can contain ASCII letters (a-z, A-Z), numbers (0-9), and hyphens (-)
    - Cannot start or end with hyphen
    - Each label (part separated by dots) must be <= 63 characters
    - Each label cannot start or end with hyphen

    Args:
        hostname: Hostname string to validate

    Returns:
        True if hostname is valid according to RFC 1123, False otherwise
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
    Convert pretty hostname to valid system hostname format.

    Converts a user-friendly hostname string into a valid system hostname
    by lowercasing, removing special characters, replacing spaces with hyphens,
    and ensuring RFC 1123 compliance.

    Args:
        pretty_hostname: The user-friendly hostname to convert
        max_length: Maximum length for resulting hostname (default 64)

    Returns:
        Sanitized hostname string suitable for system use, guaranteed to be
        valid according to RFC 1123. Falls back to 'hifiberry' if sanitization
        results in empty string or leading hyphen.
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

    logger.debug("Sanitized '%s' to '%s'", pretty_hostname, hostname)
    return hostname


def main() -> int:
    """
    Command-line interface for hostname management.

    Provides CLI access to hostname validation, sanitization, and system
    hostname management functions.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(
        description='Manage system hostname configuration'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Subcommand: get
    subparsers.add_parser(
        'get',
        help='Get current system hostname'
    )

    # Subcommand: validate
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate hostname format'
    )
    validate_parser.add_argument('hostname', help='Hostname to validate')

    # Subcommand: sanitize
    sanitize_parser = subparsers.add_parser(
        'sanitize',
        help='Convert pretty hostname to valid format'
    )
    sanitize_parser.add_argument('hostname', help='Hostname to sanitize')
    sanitize_parser.add_argument(
        '--max-length',
        type=int,
        default=64,
        help='Maximum hostname length (default: 64)'
    )

    # Subcommand: set
    set_parser = subparsers.add_parser(
        'set',
        help='Set system hostname'
    )
    set_parser.add_argument('hostname', help='New hostname to set')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == 'get':
        hostname = get_current_hostname()
        if hostname:
            print(hostname)
            return 0
        print("Failed to get hostname", file=sys.stderr)
        return 1

    if args.command == 'validate':
        if validate_hostname(args.hostname):
            print(f"'{args.hostname}' is a valid hostname")
            return 0
        print(f"'{args.hostname}' is not a valid hostname", file=sys.stderr)
        return 1

    if args.command == 'sanitize':
        sanitized = sanitize_hostname(args.hostname, args.max_length)
        print(sanitized)
        return 0

    if args.command == 'set':
        if validate_hostname(args.hostname):
            if set_hostname_with_hosts_update(args.hostname):
                print(f"Successfully set hostname to '{args.hostname}'")
                return 0
            print("Failed to set hostname", file=sys.stderr)
            return 1
        print(f"'{args.hostname}' is not a valid hostname", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
