#!/usr/bin/env python3

import os
import sys
import re
import argparse
import logging
import subprocess
import netifaces
from typing import List, Dict, Optional

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
    parser = argparse.ArgumentParser(description='Network Configuration Tool')
    
    # Command group
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument('--list-interfaces', action='store_true', 
                        help='List all physical network interfaces')
    command_group.add_argument('--set-dhcp', metavar='INTERFACE',
                        help='Configure specified interface to use DHCP')
    command_group.add_argument('--set-fixed', metavar='INTERFACE',
                        help='Configure specified interface to use static IP')
    
    # Fixed IP configuration options
    parser.add_argument('--ip', help='Fixed IP address with netmask (e.g., 192.168.1.10/24)')
    parser.add_argument('--router', help='Router/gateway address (e.g., 192.168.1.1)')
    
    # Display options
    parser.add_argument('--long', action='store_true',
                        help='Display detailed interface information in a single line')
    
    # Create mutually exclusive group for verbosity control
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress all output except warnings and errors')
    
    return parser.parse_args()

def is_physical_interface(interface: str) -> bool:
    """
    Determine if an interface is a physical interface (Ethernet or WiFi).
    
    Args:
        interface: Interface name
        
    Returns:
        True if it's a physical interface, False otherwise
    """
    # Skip loopback interfaces
    if interface.startswith('lo'):
        return False
    
    # Skip Docker interfaces
    if interface.startswith('docker') or interface.startswith('br-') or interface.startswith('veth'):
        return False
    
    # Skip virtual interfaces and other common non-physical interfaces
    if interface.startswith(('tun', 'tap', 'virbr', 'vnet', 'bond', 'dummy')):
        return False
    
    # On Linux, check if it's a wireless interface
    is_wireless = False
    try:
        with open('/proc/net/wireless', 'r') as f:
            for line in f:
                if interface in line:
                    is_wireless = True
                    break
    except Exception:
        pass  # File might not exist or not be accessible
    
    # On Linux, check if it's a physical Ethernet interface
    is_ethernet = False
    try:
        path = f"/sys/class/net/{interface}/device"
        if os.path.exists(path):
            is_ethernet = True
    except Exception:
        pass
    
    # Get interface type if possible
    interface_type = None
    try:
        # Try to get interface type using ethtool
        cmd = ['ethtool', '-i', interface]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith('driver:'):
                    interface_type = line.split(':', 1)[1].strip()
                    break
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Common wireless drivers
    wireless_drivers = ['iwlwifi', 'ath9k', 'ath10k', 'brcmfmac', 'rtl8192', 'wl']
    if interface_type and any(driver in interface_type for driver in wireless_drivers):
        is_wireless = True
    
    # If we have specific information, use it
    if is_wireless or is_ethernet:
        return True
    
    # Otherwise, make an educated guess based on naming conventions
    ethernet_patterns = [r'^eth\d+$', r'^en[ospx]\d+$', r'^ens\d+$', r'^enp\d+s\d+$']
    wifi_patterns = [r'^wlan\d+$', r'^wlp\d+s\d+$', r'^wls\d+$', r'^wifi\d+$']
    
    # Check if interface name matches common Ethernet or WiFi patterns
    for pattern in ethernet_patterns + wifi_patterns:
        if re.match(pattern, interface):
            return True
    
    # Windows interface naming is different - check for common names
    if interface.startswith(('Ethernet', 'Local Area Connection', 'Wi-Fi')):
        return True
    
    # For macOS
    if interface.startswith(('en', 'eth', 'wlan')):
        return True
    
    return False

def list_physical_interfaces() -> List[Dict[str, str]]:
    """
    List physical network interfaces (Ethernet and WiFi).
    
    Returns:
        List of dictionaries containing interface information
    """
    interfaces = []
    
    for interface in netifaces.interfaces():
        if is_physical_interface(interface):
            mac_address = None
            ipv4_address = None
            ipv4_netmask = None
            
            # Get interface addresses
            addrs = netifaces.ifaddresses(interface)
            
            # Get MAC address
            if netifaces.AF_LINK in addrs:
                mac_info = addrs[netifaces.AF_LINK][0]
                mac_address = mac_info.get('addr', None)
            
            # Get IPv4 address and netmask
            if netifaces.AF_INET in addrs:
                inet_info = addrs[netifaces.AF_INET][0]
                ipv4_address = inet_info.get('addr', None)
                ipv4_netmask = inet_info.get('netmask', None)
            
            # Get interface state if possible
            state = 'unknown'
            if ipv4_address:
                state = 'up'
            
            # Try to get more accurate state on Linux
            try:
                with open(f'/sys/class/net/{interface}/operstate', 'r') as f:
                    state = f.read().strip()
            except Exception:
                pass
            
            # Try to determine interface type
            if interface.startswith(('wlan', 'wlp', 'wls', 'wifi', 'Wi-Fi')):
                interface_type = 'wireless'
            else:
                interface_type = 'wired'
            
            interfaces.append({
                'name': interface,
                'mac': mac_address,
                'ipv4': ipv4_address,
                'netmask': ipv4_netmask,
                'state': state,
                'type': interface_type
            })
    
    return interfaces

def configure_dhcp(interface: str) -> bool:
    """
    Configure the specified interface to use DHCP using NetworkManager.
    
    Args:
        interface: The interface name to configure
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Check if NetworkManager is available and running
    try:
        cmd = ['systemctl', 'is-active', 'NetworkManager']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.error("NetworkManager is not running")
            return False
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("Failed to check NetworkManager status")
        return False
    
    # Check if the interface exists and is a physical interface
    if not is_physical_interface(interface):
        logger.error(f"{interface} is not a valid physical network interface")
        return False
    
    logger.info(f"Configuring {interface} to use DHCP")
    
    # Get current connection name for interface, if any
    connection_name = None
    try:
        cmd = ['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) == 2 and parts[1] == interface:
                        connection_name = parts[0]
                        logger.debug(f"Found active connection '{connection_name}' for {interface}")
                        break
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Failed to get active connections: {e}")
        return False
    
    try:
        if connection_name:
            # Modify existing connection
            logger.debug(f"Modifying existing connection {connection_name}")
            cmd = ['nmcli', 'connection', 'modify', connection_name, 
                   'ipv4.method', 'auto', 'ipv4.addresses', '', 'ipv4.gateway', '']
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error(f"Failed to modify connection: {result.stderr}")
                return False
                
            # Apply changes by reactivating the connection
            logger.debug(f"Reactivating connection {connection_name}")
            cmd = ['nmcli', 'connection', 'up', connection_name]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to reactivate connection: {result.stderr}")
                return False
        else:
            # Create a new connection
            logger.debug(f"Creating new DHCP connection for {interface}")
            connection_name = f"dhcp-{interface}"
            cmd = ['nmcli', 'connection', 'add', 'type', 'ethernet', 'con-name', connection_name,
                   'ifname', interface, 'ipv4.method', 'auto']
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error(f"Failed to create connection: {result.stderr}")
                return False
                
            # Activate the new connection
            logger.debug(f"Activating new connection {connection_name}")
            cmd = ['nmcli', 'connection', 'up', connection_name]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to activate connection: {result.stderr}")
                return False
    
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error configuring DHCP: {e}")
        return False
    
    logger.info(f"Successfully configured {interface} to use DHCP")
    return True

def configure_fixed_ip(interface: str, ip_with_mask: str, router: str) -> bool:
    """
    Configure the specified interface to use a static IP address.
    
    Args:
        interface: The interface name to configure
        ip_with_mask: IP address with netmask (e.g., 192.168.1.10/24)
        router: Router/gateway address
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Check if NetworkManager is available and running
    try:
        cmd = ['systemctl', 'is-active', 'NetworkManager']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.error("NetworkManager is not running")
            return False
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("Failed to check NetworkManager status")
        return False
    
    # Check if the interface exists and is a physical interface
    if not is_physical_interface(interface):
        logger.error(f"{interface} is not a valid physical network interface")
        return False
    
    # Validate IP/mask format
    if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', ip_with_mask):
        logger.error(f"Invalid IP/mask format: {ip_with_mask}. Expected format: 192.168.1.10/24")
        return False
    
    # Validate router address format
    if not re.match(r'^\d+\.\d+\.\d+\.\d+$', router):
        logger.error(f"Invalid router address: {router}. Expected format: 192.168.1.1")
        return False
    
    logger.info(f"Configuring {interface} with static IP {ip_with_mask} and router {router}")
    
    # Get current connection name for interface, if any
    connection_name = None
    try:
        cmd = ['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) == 2 and parts[1] == interface:
                        connection_name = parts[0]
                        logger.debug(f"Found active connection '{connection_name}' for {interface}")
                        break
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Failed to get active connections: {e}")
        return False
    
    try:
        if connection_name:
            # Modify existing connection
            logger.debug(f"Modifying existing connection {connection_name}")
            cmd = ['nmcli', 'connection', 'modify', connection_name, 
                   'ipv4.method', 'manual', 'ipv4.addresses', ip_with_mask, 
                   'ipv4.gateway', router]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error(f"Failed to modify connection: {result.stderr}")
                return False
                
            # Apply changes by reactivating the connection
            logger.debug(f"Reactivating connection {connection_name}")
            cmd = ['nmcli', 'connection', 'up', connection_name]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to reactivate connection: {result.stderr}")
                return False
        else:
            # Create a new connection
            logger.debug(f"Creating new static IP connection for {interface}")
            connection_name = f"static-{interface}"
            cmd = ['nmcli', 'connection', 'add', 'type', 'ethernet', 'con-name', connection_name,
                   'ifname', interface, 'ipv4.method', 'manual', 'ipv4.addresses', ip_with_mask,
                   'ipv4.gateway', router]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error(f"Failed to create connection: {result.stderr}")
                return False
                
            # Activate the new connection
            logger.debug(f"Activating new connection {connection_name}")
            cmd = ['nmcli', 'connection', 'up', connection_name]
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to activate connection: {result.stderr}")
                return False
    
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error configuring static IP: {e}")
        return False
    
    logger.info(f"Successfully configured {interface} with static IP {ip_with_mask}")
    return True

def main():
    """Main function to run when script is executed directly."""
    args = parse_arguments()
    
    # Configure logging based on verbosity
    setup_logging(args.verbose, args.quiet)
    
    if args.list_interfaces:
        interfaces = list_physical_interfaces()
        
        if interfaces:
            logger.debug(f"Found {len(interfaces)} physical interfaces")
            
            for interface in interfaces:
                name = interface['name']
                mac = interface['mac'] if interface['mac'] else 'Unknown'
                ipv4 = interface['ipv4'] if interface['ipv4'] else 'Not configured'
                state = interface['state']
                iface_type = interface['type']
                
                # Log detailed info at debug level
                logger.debug(f"Interface: {name} ({iface_type})")
                logger.debug(f"  MAC Address: {mac}")
                logger.debug(f"  IPv4 Address: {ipv4}")
                logger.debug(f"  State: {state}")
                
                if args.long:
                    # Single line with detailed information
                    print(f"{name} | {iface_type} | {mac} | {ipv4} | {state}")
                else:
                    # Simple output - just the interface name
                    print(name)
        else:
            logger.warning("No physical network interfaces found")
    
    elif args.set_dhcp:
        interface = args.set_dhcp
        if configure_dhcp(interface):
            logger.info(f"Interface {interface} configured to use DHCP")
            sys.exit(0)
        else:
            logger.error(f"Failed to configure DHCP on interface {interface}")
            sys.exit(1)
    
    elif args.set_fixed:
        interface = args.set_fixed
        
        # Check for required arguments
        if not args.ip or not args.router:
            logger.error("--set-fixed requires --ip and --router arguments")
            sys.exit(1)
        
        ip_with_mask = args.ip
        router = args.router
        
        if configure_fixed_ip(interface, ip_with_mask, router):
            logger.info(f"Interface {interface} configured with static IP {ip_with_mask} and router {router}")
            sys.exit(0)
        else:
            logger.error(f"Failed to configure static IP on interface {interface}")
            sys.exit(1)

if __name__ == "__main__":
    main()
