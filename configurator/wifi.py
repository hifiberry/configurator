#!/usr/bin/env python3

import sys
import os
import re
import argparse
import logging
import subprocess
import time
from typing import List, Dict, Optional, Any

# Set up logging
logger = logging.getLogger(__name__)

def setup_logging(verbose=False, quiet=False):
    """Configure logging based on verbosity level."""
    if quiet:
        log_level = logging.WARNING
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(log_level)
    
    # Create formatter and add it to the handler
    if verbose:
        formatter = logging.Formatter('%(levelname)s: %(message)s')
    else:
        formatter = logging.Formatter('%(message)s')
    
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    root_logger.addHandler(console_handler)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='WiFi Network Management Tool')
    
    # Command group
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument('--list-networks', action='store_true', 
                        help='List available WiFi networks')
    command_group.add_argument('--connect', metavar='SSID',
                        help='Connect to specified WiFi network')
    command_group.add_argument('--show-current', action='store_true',
                        help='Show currently connected WiFi network')
    
    # Scan options
    parser.add_argument('--timeout', type=int, default=10, 
                        help='Maximum scanning time in seconds (default: 10)')
    
    # Connection options
    parser.add_argument('--passphrase', help='Passphrase for the WiFi network')
    parser.add_argument('--revert-when-fail', action='store_true',
                        help='Revert to previous connection if new connection fails')
    
    # Display options
    parser.add_argument('--long', action='store_true',
                        help='Display detailed network information')
    
    # Create mutually exclusive group for verbosity control
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress all output except warnings and errors')
    
    return parser.parse_args()

def find_wireless_interfaces() -> List[str]:
    """
    Find available wireless interfaces.
    
    Returns:
        List of wireless interface names
    """
    interfaces = []
    
    # Try using iw to find wireless interfaces
    try:
        cmd = ['iw', 'dev']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            current_interface = None
            for line in result.stdout.splitlines():
                if 'Interface' in line:
                    current_interface = line.split('Interface', 1)[1].strip()
                    interfaces.append(current_interface)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # If iw failed or didn't find interfaces, try using NetworkManager
    if not interfaces:
        try:
            cmd = ['nmcli', '-t', '-f', 'DEVICE,TYPE', 'device']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if ':wifi' in line:
                        interface = line.split(':', 1)[0]
                        interfaces.append(interface)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    
    # If still nothing found, try checking wireless directory in /proc/net
    if not interfaces:
        try:
            if os.path.exists('/proc/net/wireless'):
                with open('/proc/net/wireless', 'r') as f:
                    for line in f:
                        # Skip header lines
                        if 'Inter-' in line or 'face' in line or '|' in line:
                            continue
                        
                        parts = line.strip().split()
                        if parts:
                            # The interface name is the first field, often with a colon
                            interface = parts[0].rstrip(':')
                            interfaces.append(interface)
        except Exception:
            pass
    
    return interfaces

def scan_wifi_networks(timeout: int = 10) -> List[Dict[str, Any]]:
    """
    Scan for available WiFi networks.
    
    Args:
        timeout: Maximum scanning time in seconds
        
    Returns:
        List of dictionaries containing network information
    """
    networks = []
    
    # Find wireless interfaces
    wireless_interfaces = find_wireless_interfaces()
    
    if not wireless_interfaces:
        logger.error("No wireless interfaces found")
        return networks
    
    # Use the first wireless interface found for scanning
    interface = wireless_interfaces[0]
    logger.debug(f"Using wireless interface: {interface}")
    
    # Try using NetworkManager for scanning (preferred method)
    nm_available = False
    try:
        cmd = ['systemctl', 'is-active', 'NetworkManager']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        nm_available = result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    if nm_available:
        logger.debug("Using NetworkManager to scan for networks")
        networks = scan_with_networkmanager(interface, timeout)
    else:
        # Fall back to iw for scanning
        logger.debug("Using iw to scan for networks")
        networks = scan_with_iw(interface, timeout)
    
    # Sort networks by signal strength (strongest first)
    networks.sort(key=lambda x: x.get('signal', 0), reverse=True)
    
    return networks

def scan_with_networkmanager(interface: str, timeout: int) -> List[Dict[str, Any]]:
    """
    Scan for WiFi networks using NetworkManager.
    
    Args:
        interface: Wireless interface name
        timeout: Maximum scanning time in seconds
        
    Returns:
        List of dictionaries containing network information
    """
    networks = []
    
    try:
        # Start a scan
        cmd = ['nmcli', 'device', 'wifi', 'rescan', 'ifname', interface]
        logger.debug(f"Running command: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, timeout=2)
        
        # Wait for scan to complete (with timeout)
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(1)
            
            # Get scan results
            cmd = ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,CHAN,BSSID,BARS', 
                   'device', 'wifi', 'list', 'ifname', interface]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout:
                break
        
        # Parse scan results
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                fields = line.split(':')
                if len(fields) >= 5:
                    ssid = fields[0]
                    signal = int(fields[1]) if fields[1].isdigit() else 0
                    security = fields[2] if fields[2] else 'Open'
                    channel = fields[3] if len(fields) > 3 else ''
                    bssid = fields[4] if len(fields) > 4 else ''
                    
                    # Skip networks with empty SSID
                    if not ssid:
                        continue
                    
                    networks.append({
                        'ssid': ssid,
                        'signal': signal,
                        'security': security,
                        'channel': channel,
                        'bssid': bssid
                    })
                    logger.debug(f"Found network: {ssid} ({signal}%)")
    
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error scanning with NetworkManager: {e}")
    
    return networks

def scan_with_iw(interface: str, timeout: int) -> List[Dict[str, Any]]:
    """
    Scan for WiFi networks using iw.
    
    Args:
        interface: Wireless interface name
        timeout: Maximum scanning time in seconds
        
    Returns:
        List of dictionaries containing network information
    """
    networks = []
    
    try:
        # Start a scan
        logger.debug(f"Starting WiFi scan on {interface} with iw")
        cmd = ['iw', 'dev', interface, 'scan']
        
        # Set a timeout slightly longer than requested to account for the scan itself
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        
        if result.returncode == 0:
            current_network = None
            current_bss = None
            
            for line in result.stdout.splitlines():
                line = line.strip()
                
                # New BSS (Basic Service Set) indicates a new network
                if line.startswith('BSS '):
                    # Save previous network if we have one
                    if current_network and 'ssid' in current_network:
                        networks.append(current_network)
                    
                    # Extract BSSID (MAC address)
                    bssid = line.split('BSS ', 1)[1].split('(', 1)[0].strip()
                    current_network = {'bssid': bssid}
                    current_bss = bssid
                
                # Extract SSID
                elif 'SSID: ' in line:
                    ssid = line.split('SSID: ', 1)[1]
                    # Skip networks with empty SSID
                    if ssid:
                        current_network['ssid'] = ssid
                
                # Extract signal strength
                elif 'signal: ' in line:
                    signal_str = line.split('signal: ', 1)[1].split(' ', 1)[0]
                    try:
                        # Convert dBm to percentage (approximate)
                        signal_dbm = float(signal_str)
                        signal_percent = min(100, max(0, int((signal_dbm + 100) * 2)))
                        current_network['signal'] = signal_percent
                    except ValueError:
                        current_network['signal'] = 0
                
                # Extract channel
                elif 'freq: ' in line:
                    freq = line.split('freq: ', 1)[1]
                    # Convert frequency to channel (approximate)
                    try:
                        freq_num = int(freq)
                        # 2.4 GHz band
                        if 2412 <= freq_num <= 2484:
                            channel = (freq_num - 2407) // 5
                        # 5 GHz band
                        elif freq_num >= 5000:
                            channel = (freq_num - 5000) // 5
                        else:
                            channel = 0
                        current_network['channel'] = str(channel)
                    except ValueError:
                        current_network['channel'] = ''
                
                # Extract security information
                elif 'capability: ' in line:
                    if 'Privacy' in line:
                        current_network['security'] = 'Protected'
                    else:
                        current_network['security'] = 'Open'
                
                # Additional security information
                elif 'RSN' in line or 'WPA' in line:
                    current_network['security'] = 'WPA'
            
            # Add the last network
            if current_network and 'ssid' in current_network:
                networks.append(current_network)
    
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error scanning with iw: {e}")
    
    return networks

def save_current_connection() -> Optional[Dict[str, Any]]:
    """
    Save information about the current WiFi connection.
    
    Returns:
        Dictionary with current connection details or None if not connected
    """
    # Get the current active connection
    try:
        cmd = ['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE', 'connection', 'show', '--active']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ':wifi' in line:
                    fields = line.split(':')
                    if len(fields) >= 2:
                        connection_name = fields[0]
                        device = fields[1]
                        
                        logger.debug(f"Found active WiFi connection: {connection_name} on {device}")
                        
                        # Get connection details
                        cmd = ['nmcli', '-t', 'connection', 'show', connection_name]
                        details = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        
                        if details.returncode == 0:
                            connection_info = {
                                'name': connection_name,
                                'device': device,
                                'id': connection_name
                            }
                            
                            # Parse connection details
                            for detail_line in details.stdout.splitlines():
                                if ':' in detail_line:
                                    key, value = detail_line.split(':', 1)
                                    if 'ssid' in key.lower():
                                        connection_info['ssid'] = value
                            
                            return connection_info
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error saving current connection: {e}")
    
    return None

def get_current_connection() -> Optional[Dict[str, Any]]:
    """
    Get information about the current WiFi connection.
    
    Returns:
        Dictionary with current connection details or None if not connected
    """
    # Get the current active connection
    try:
        cmd = ['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE,ACTIVE', 'connection', 'show']
        logging.debug("Getting current WiFi connection using command: " + ' '.join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # Check for both wireless type formats and ensure connection is active
                if (':802-11-wireless:' in line and ':yes' in line) or (':wifi:' in line and ':yes' in line):
                    fields = line.split(':')
                    if len(fields) >= 3:
                        connection_name = fields[0]
                        device = fields[1]
                        
                        logger.debug(f"Found active WiFi connection: {connection_name} on {device}")
                        
                        # Get connection details
                        cmd = ['nmcli', '-t', 'connection', 'show', connection_name]
                        logger.debug(f"Getting connection details: {' '.join(cmd)}")
                        details = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        
                        if details.returncode == 0:
                            connection_info = {
                                'name': connection_name,
                                'device': device,
                                'id': connection_name,
                                'ssid': connection_name,  # Default to connection name
                                'security': 'Unknown'
                            }
                            
                            # Extract SSID from connection details - the correct 802-11-wireless.ssid field
                            ssid = None
                            for detail_line in details.stdout.splitlines():
                                # Get SSID from the exact field (802-11-wireless.ssid)
                                if detail_line.startswith('802-11-wireless.ssid:'):
                                    ssid = detail_line.split(':', 1)[1].strip()
                                    if ssid:  # Only use non-empty values
                                        connection_info['ssid'] = ssid
                                        logger.debug(f"Found SSID from correct field: {ssid}")
                                        break
                            
                            # Get security type
                            for detail_line in details.stdout.splitlines():
                                if detail_line.startswith('802-11-wireless-security.key-mgmt:'):
                                    security = detail_line.split(':', 1)[1].strip()
                                    if security:
                                        connection_info['security'] = security
                                        logger.debug(f"Found security type: {security}")
                                    break
                            
                            # Try to get IP address
                            try:
                                # Query for the IP address directly
                                ip_cmd = ['nmcli', '-t', '-f', 'IP4.ADDRESS', 'connection', 'show', connection_name]
                                logger.debug(f"Getting IP information: {' '.join(ip_cmd)}")
                                ip_result = subprocess.run(ip_cmd, capture_output=True, text=True, timeout=3)
                                
                                if ip_result.returncode == 0:
                                    ip_address = None
                                    for line in ip_result.stdout.splitlines():
                                        if line.startswith('IP4.ADDRESS'):
                                            ip_parts = line.split(':', 1)[1].strip()
                                            if ip_parts:
                                                # Extract the IP address part before the subnet mask
                                                ip_address = ip_parts.split('/')[0]
                                                connection_info['ip'] = ip_address
                                                logger.debug(f"Found IP address: {ip_address}")
                                                break
                            except Exception as e:
                                logger.debug(f"Failed to get IP address: {e}")
                            
                            # If we still don't have an SSID (unlikely), try alternate methods
                            if not ssid:
                                # Use iwconfig as a fallback
                                try:
                                    logger.debug(f"Trying iwconfig to get SSID for {device}")
                                    iw_cmd = ['iwconfig', device]
                                    iw_result = subprocess.run(iw_cmd, capture_output=True, text=True, timeout=3)
                                    
                                    if iw_result.returncode == 0 and iw_result.stdout:
                                        for iw_line in iw_result.stdout.splitlines():
                                            if 'ESSID:' in iw_line:
                                                essid = iw_line.split('ESSID:', 1)[1].strip('"')
                                                if essid and essid != "off/any":
                                                    connection_info['ssid'] = essid
                                                    logger.debug(f"Found ESSID via iwconfig: {essid}")
                                                    break
                                except Exception as e:
                                    logger.debug(f"Failed to get ESSID from iwconfig: {e}")
                            
                            return connection_info
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error getting current connection: {e}")
    
    return None

def connect_to_wifi(ssid: str, passphrase: Optional[str] = None, 
                  revert_on_failure: bool = False) -> bool:
    """
    Connect to a WiFi network.
    
    Args:
        ssid: The network SSID to connect to
        passphrase: Optional passphrase for protected networks
        revert_on_failure: Whether to revert to previous connection if this one fails
        
    Returns:
        True if connection was successful, False otherwise
    """
    # Check if NetworkManager is running
    try:
        cmd = ['systemctl', 'is-active', 'NetworkManager']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.error("NetworkManager is not running")
            return False
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error checking NetworkManager status: {e}")
        return False

    # Find wireless interfaces
    wireless_interfaces = find_wireless_interfaces()
    
    if not wireless_interfaces:
        logger.error("No wireless interfaces found")
        return False

    # Use the first wireless interface
    interface = wireless_interfaces[0]
    logger.debug(f"Using wireless interface: {interface}")
    
    # Save current connection if revert is requested
    old_connection = None
    if revert_on_failure:
        old_connection = save_current_connection()
        if old_connection:
            logger.debug(f"Saved current connection: {old_connection.get('name', 'Unknown')}")
        else:
            logger.debug("No current WiFi connection to save")

    # Connect to the network
    try:
        # Check if we've connected to this network before
        cmd = ['nmcli', '-t', '-f', 'NAME', 'connection', 'show']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        connection_exists = False
        connection_name = ""
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line == ssid or line.startswith(f"{ssid}:"):
                    connection_exists = True
                    connection_name = line.split(':', 1)[0]
                    logger.debug(f"Found existing connection profile: {connection_name}")
                    break
        
        if connection_exists:
            # Use existing connection
            logger.info(f"Connecting to {ssid} using existing profile")
            cmd = ['nmcli', 'connection', 'up', connection_name]
            connect_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if connect_result.returncode != 0:
                logger.error(f"Failed to connect to {ssid}: {connect_result.stderr}")
                return _handle_connection_failure(old_connection, revert_on_failure)
        else:
            # Create new connection
            if passphrase:
                logger.info(f"Connecting to {ssid} with password")
                cmd = ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', passphrase, 'ifname', interface]
            else:
                logger.info(f"Connecting to {ssid} (open network)")
                cmd = ['nmcli', 'device', 'wifi', 'connect', ssid, 'ifname', interface]
            
            # Run connection command
            logging.debug(f"Running command: {' '.join(cmd)}")
            # Use subprocess.run to execute the command
            connect_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if connect_result.returncode != 0:
                logger.error(f"Failed to connect to {ssid}: {connect_result.stderr}")
                return _handle_connection_failure(old_connection, revert_on_failure)
        
        # Verify connection was successful by checking active connections
        cmd = ['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show', '--active']
        logging.debug(f"Running command for verification: {' '.join(cmd)}")
        verify_result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if verify_result.returncode == 0:
            # Check if any WiFi connection is active
            has_active_wifi = False
            
            for line in verify_result.stdout.splitlines():
                if ':802-11-wireless' in line or ':wifi' in line:
                    has_active_wifi = True
                    active_conn_name = line.split(':', 1)[0]
                    logger.debug(f"Found active WiFi connection: {active_conn_name}")
                    break
            
            if has_active_wifi:
                # Now verify this is the connection we want by checking its properties
                cmd = ['nmcli', '-t', '-f', 'connection.id,802-11-wireless.ssid', 'connection', 'show', active_conn_name]
                logger.debug(f"Running command to check SSID: {' '.join(cmd)}")
                conn_details = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if conn_details.returncode == 0:
                    for line in conn_details.stdout.splitlines():
                        if 'ssid' in line.lower():
                            _, conn_ssid = line.split(':', 1)
                            if conn_ssid == ssid:
                                logger.info(f"Successfully connected to {ssid}")
                                return True
                
                # Alternative method: check device connection
                cmd = ['nmcli', '-t', '-f', 'GENERAL.CONNECTION', 'device', 'show', wireless_interfaces[0]]
                logger.debug(f"Running command to check device connection: {' '.join(cmd)}")
                device_details = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if device_details.returncode == 0:
                    for line in device_details.stdout.splitlines():
                        if ':' in line:
                            _, conn_name = line.split(':', 1)
                            logger.debug(f"Device is connected to: {conn_name}")
                            # If we just activated a connection and the device is connected, assume success
                            if conn_name:
                                logger.info(f"Device is connected to network, assuming success")
                                return True
            
            logger.error(f"Failed to verify connection to {ssid}")
            return _handle_connection_failure(old_connection, revert_on_failure)
        else:
            logger.error("Failed to verify active connections")
            return _handle_connection_failure(old_connection, revert_on_failure)
            
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error connecting to WiFi network: {e}")
        return _handle_connection_failure(old_connection, revert_on_failure)
    
    # We shouldn't get here, but return False as default
    return False

def _handle_connection_failure(old_connection: Optional[Dict[str, Any]], 
                               revert_on_failure: bool) -> bool:
    """
    Handle a connection failure, potentially reverting to previous connection.
    
    Args:
        old_connection: The previous connection information
        revert_on_failure: Whether to revert to previous connection
        
    Returns:
        False (indicating connection failure)
    """
    if revert_on_failure and old_connection and 'name' in old_connection:
        logger.info(f"Reverting to previous connection: {old_connection['name']}")
        try:
            cmd = ['nmcli', 'connection', 'up', old_connection['name']]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"Successfully reverted to {old_connection['name']}")
            else:
                logger.error(f"Failed to revert to previous connection: {result.stderr}")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"Error reverting to previous connection: {e}")
    
    return False

def main():
    """Main function to run when script is executed directly."""
    args = parse_arguments()
    
    # Configure logging based on verbosity
    setup_logging(args.verbose, args.quiet)
    
    if args.list_networks:
        logger.info(f"Scanning for WiFi networks (timeout: {args.timeout}s)...")
        networks = scan_wifi_networks(args.timeout)
        
        if networks:
            logger.info(f"Found {len(networks)} WiFi networks")
            
            # Print network information
            for network in networks:
                ssid = network.get('ssid', 'Unknown')
                signal = network.get('signal', 0)
                security = network.get('security', 'Unknown')
                channel = network.get('channel', '')
                bssid = network.get('bssid', '')
                
                # Log detailed info at debug level
                logger.debug(f"Network: {ssid}")
                logger.debug(f"  BSSID: {bssid}")
                logger.debug(f"  Signal: {signal}%")
                logger.debug(f"  Security: {security}")
                logger.debug(f"  Channel: {channel}")
                
                if args.long:
                    # Pipe-separated format with all details
                    print(f"{ssid}|{signal}|{security}|{channel}|{bssid}")
                else:
                    # Pipe-separated format with SSID, signal and security
                    print(f"{ssid}|{signal}|{security}")
        else:
            logger.warning("No WiFi networks found")
    
    elif args.connect:
        ssid = args.connect
        passphrase = args.passphrase
        revert_on_failure = args.revert_when_fail
        
        logger.info(f"Attempting to connect to WiFi network: {ssid}")
        
        if connect_to_wifi(ssid, passphrase, revert_on_failure):
            # Successfully connected
            sys.exit(0)
        else:
            # Failed to connect
            sys.exit(1)
    
    elif args.show_current:
        connection = get_current_connection()
        
        if connection:
            ssid = connection.get('ssid', 'Unknown')
            device = connection.get('device', 'Unknown')
            ip = connection.get('ip', 'Unknown')
            security = connection.get('security', 'Unknown')
            
            logger.info(f"Currently connected to WiFi network: {ssid}")
            
            if args.long:
                # Detailed output
                print(f"{ssid}|{device}|{ip}|{security}")
            else:
                # Simple output
                print(f"{ssid}|{ip}")
        else:
            logger.warning("Not currently connected to any WiFi network")
            sys.exit(1)

if __name__ == "__main__":
    main()
