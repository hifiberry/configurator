#!/usr/bin/env python3
"""
Avahi Configuration Module

This module provides functionality to configure the Avahi daemon
to only advertise on physical network interfaces (eth*, wlan*).
"""

import os
import sys
import argparse
import logging
import shutil
import subprocess


def setup_logging(verbose=False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
        stream=sys.stderr
    )


def configure_avahi_interfaces():
    """
    Configure Avahi daemon to only advertise on physical interfaces (eth*, wlan*)
    
    This function modifies /etc/avahi/avahi-daemon.conf to:
    - Allow only physical ethernet and wireless interfaces
    
    Returns:
        True if successful, False otherwise
    """
    avahi_conf = "/etc/avahi/avahi-daemon.conf"
    
    try:
        # Check if Avahi is installed
        if not os.path.exists(avahi_conf):
            logging.info("Avahi daemon not installed, skipping configuration")
            return True
        
        # Read current configuration
        with open(avahi_conf, 'r') as f:
            lines = f.readlines()
        
        # Track if we need to modify the file
        modified = False
        new_lines = []
        in_server_section = False
        found_allow_interfaces = False
        found_deny_interfaces = False
        
        for line in lines:
            stripped = line.strip()
            
            # Track if we're in the [server] section
            if stripped.startswith('[server]'):
                in_server_section = True
                new_lines.append(line)
                continue
            elif stripped.startswith('[') and stripped.endswith(']'):
                in_server_section = False
                new_lines.append(line)
                continue
            
            # Skip existing allow-interfaces and deny-interfaces lines
            if in_server_section and (stripped.startswith('allow-interfaces=') or 
                                    stripped.startswith('#allow-interfaces=')):
                found_allow_interfaces = True
                modified = True
                continue
            elif in_server_section and (stripped.startswith('deny-interfaces=') or 
                                       stripped.startswith('#deny-interfaces=')):
                found_deny_interfaces = True
                modified = True
                continue
            
            new_lines.append(line)
        
        # Add our interface configuration to the [server] section
        if in_server_section or not found_allow_interfaces:
            # Find the [server] section and add our configuration
            final_lines = []
            in_server_section = False
            server_section_processed = False
            
            for line in new_lines:
                stripped = line.strip()
                
                if stripped.startswith('[server]'):
                    in_server_section = True
                    server_section_processed = False
                    final_lines.append(line)
                    continue
                elif stripped.startswith('[') and stripped.endswith(']'):
                    # End of server section, add our config if not already done
                    if in_server_section and not server_section_processed:
                        final_lines.append('allow-interfaces=eth0,wlan0\n')
                        server_section_processed = True
                        modified = True
                    in_server_section = False
                    final_lines.append(line)
                    continue
                
                final_lines.append(line)
            
            # If we're still in server section at end of file, add our config
            if in_server_section and not server_section_processed:
                final_lines.append('allow-interfaces=eth0,wlan0\n')
                modified = True
            
            new_lines = final_lines
        
        # Write the modified configuration if changes were made
        if modified:
            # Create backup
            backup_file = f"{avahi_conf}.backup"
            if not os.path.exists(backup_file):
                shutil.copy2(avahi_conf, backup_file)
                logging.info(f"Created backup: {backup_file}")
            
            # Write new configuration
            with open(avahi_conf, 'w') as f:
                f.writelines(new_lines)
            
            logging.info("Updated Avahi configuration to only advertise on physical interfaces")
            
            # Restart Avahi daemon to apply changes
            logging.info("Restarting Avahi daemon to apply configuration changes")
            try:
                # First check if the service is active
                check_result = subprocess.run(
                    ['systemctl', 'is-active', 'avahi-daemon'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if check_result.returncode == 0:
                    # Service is active, restart it
                    result = subprocess.run(
                        ['systemctl', 'restart', 'avahi-daemon'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0:
                        logging.info("Restarted Avahi daemon successfully")
                    else:
                        logging.warning(f"Failed to restart Avahi daemon: {result.stderr.strip()}")
                        return False
                else:
                    # Service is not active, try to start it
                    logging.info("Avahi daemon is not running, attempting to start it")
                    result = subprocess.run(
                        ['systemctl', 'start', 'avahi-daemon'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0:
                        logging.info("Started Avahi daemon successfully")
                    else:
                        logging.warning(f"Failed to start Avahi daemon: {result.stderr.strip()}")
                        logging.info("Configuration updated but daemon could not be started")
                        # Don't return False here as the configuration was still updated
                        
            except Exception as e:
                logging.warning(f"Error restarting Avahi daemon: {e}")
                logging.info("Configuration updated but daemon restart failed")
                # Don't return False here as the configuration was still updated
        else:
            logging.info("Avahi configuration already correct")
        
        return True
        
    except Exception as e:
        logging.error(f"Error configuring Avahi daemon: {e}")
        return False


def check_root_privileges():
    """
    Check if the script is running as root
    
    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root (use sudo)")
        return False
    return True


def main():
    """Main function for config-avahi command"""
    parser = argparse.ArgumentParser(
        description='Configure Avahi daemon to only advertise on physical interfaces'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check current configuration, do not modify'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Check if running as root (required for modifications)
    if not args.check_only and not check_root_privileges():
        return 1
    
    if args.check_only:
        # Just check current configuration
        avahi_conf = "/etc/avahi/avahi-daemon.conf"
        if not os.path.exists(avahi_conf):
            print("Avahi daemon not installed")
            return 0
        
        try:
            with open(avahi_conf, 'r') as f:
                content = f.read()
                
            if 'allow-interfaces=eth0,wlan0' in content:
                print("Avahi configuration is correct - only advertising on physical interfaces")
                return 0
            else:
                print("Avahi configuration needs updating")
                return 1
        except Exception as e:
            logging.error(f"Error reading Avahi configuration: {e}")
            return 1
    else:
        # Configure Avahi
        if configure_avahi_interfaces():
            logging.info("Avahi configuration completed successfully")
            return 0
        else:
            logging.error("Avahi configuration failed")
            return 1


if __name__ == "__main__":
    sys.exit(main())
