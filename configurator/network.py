#!/usr/bin/env python3

import os
import sys
import re
import argparse
import logging
import subprocess
import netifaces
from typing import List, Dict, Optional
from .cmdline import CmdlineTxt

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
    command_group.add_argument('--enable-ipv6', action='store_true',
                        help='Enable IPv6 system-wide on all interfaces (persistent across reboots)')
    command_group.add_argument('--disable-ipv6', action='store_true',
                        help='Disable IPv6 system-wide on all interfaces (persistent across reboots)')
    
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

def enable_ipv6() -> bool:
    """
    Enable IPv6 system-wide on all interfaces and make it persistent across reboots.
    
    This function configures IPv6 at multiple levels to ensure comprehensive enablement:
    1. Removes ipv6.disable=1 from kernel command line (cmdline.txt)
    2. Removes any sysctl configurations that disable IPv6
    3. Creates sysctl configuration to explicitly enable IPv6
    4. Enables IPv6 on all NetworkManager connections
    5. Restarts NetworkManager to apply changes immediately
    
    The changes persist across reboots through:
    - Kernel command line parameters in /boot/firmware/cmdline.txt or /boot/cmdline.txt
    - Sysctl configuration files in /etc/sysctl.d/
    - NetworkManager connection profiles
    
    Returns:
        bool: True if successful, False otherwise
        
    Note:
        A reboot may be required for kernel-level changes to take full effect.
    """
    logger.info("Enabling IPv6 system-wide")
    
    # Remove IPv6 disable parameters from kernel parameters
    try:
        cmdline = CmdlineTxt()
        cmdline.enable_ipv6()
        cmdline.save()
        logger.info("Updated kernel command line to enable IPv6")
    except Exception as e:
        logger.warning(f"Failed to update kernel command line: {e}")
    
    # Remove sysctl settings that disable IPv6
    sysctl_file = '/etc/sysctl.d/99-disable-ipv6.conf'
    if os.path.exists(sysctl_file):
        try:
            os.remove(sysctl_file)
            logger.info("Removed IPv6 disable sysctl configuration")
        except Exception as e:
            logger.error(f"Failed to remove {sysctl_file}: {e}")
            return False
    
    # Create sysctl configuration to ensure IPv6 is enabled
    enable_sysctl_file = '/etc/sysctl.d/99-enable-ipv6.conf'
    try:
        with open(enable_sysctl_file, 'w') as f:
            f.write("# Enable IPv6\n")
            f.write("net.ipv6.conf.all.disable_ipv6 = 0\n")
            f.write("net.ipv6.conf.default.disable_ipv6 = 0\n")
            f.write("net.ipv6.conf.lo.disable_ipv6 = 0\n")
        logger.info("Created IPv6 enable sysctl configuration")
    except Exception as e:
        logger.error(f"Failed to create {enable_sysctl_file}: {e}")
        return False
    
    # Apply sysctl settings immediately
    try:
        cmd = ['sysctl', '-p', enable_sysctl_file]
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"Failed to apply sysctl settings: {result.stderr}")
            return False
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error applying sysctl settings: {e}")
        return False
    
    # Enable IPv6 on all NetworkManager connections
    success = True
    try:
        # Get all connections
        cmd = ['nmcli', '-t', '-f', 'NAME', 'connection', 'show']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            connections = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            
            for connection_name in connections:
                try:
                    # Enable IPv6 for each connection
                    cmd = ['nmcli', 'connection', 'modify', connection_name, 'ipv6.method', 'auto']
                    logger.debug(f"Running command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode != 0:
                        logger.warning(f"Failed to enable IPv6 on connection {connection_name}: {result.stderr}")
                        success = False
                    else:
                        logger.debug(f"Enabled IPv6 on connection {connection_name}")
                except Exception as e:
                    logger.warning(f"Error enabling IPv6 on connection {connection_name}: {e}")
                    success = False
        else:
            logger.warning("Failed to get NetworkManager connections")
            success = False
            
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Error configuring NetworkManager connections: {e}")
        success = False
    
    # Restart NetworkManager to apply changes
    try:
        cmd = ['systemctl', 'restart', 'NetworkManager']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"Failed to restart NetworkManager: {result.stderr}")
        else:
            logger.info("Restarted NetworkManager")
    except Exception as e:
        logger.warning(f"Error restarting NetworkManager: {e}")
    
    if success:
        logger.info("Successfully enabled IPv6 system-wide")
        return True
    else:
        logger.error("IPv6 enabled with some warnings - check logs for details")
        return False

def disable_ipv6() -> bool:
    """
    Disable IPv6 system-wide on all interfaces and make it persistent across reboots.
    
    This function configures IPv6 at multiple levels to ensure comprehensive disabling:
    1. Adds ipv6.disable=1 to kernel command line (cmdline.txt)
    2. Creates sysctl configuration to disable IPv6
    3. Removes any sysctl configurations that enable IPv6
    4. Disables IPv6 on all NetworkManager connections
    5. Restarts NetworkManager to apply changes immediately
    
    The changes persist across reboots through:
    - Kernel command line parameters in /boot/firmware/cmdline.txt or /boot/cmdline.txt
    - Sysctl configuration files in /etc/sysctl.d/
    - NetworkManager connection profiles
    
    Returns:
        bool: True if successful, False otherwise
        
    Note:
        A reboot is required for kernel-level IPv6 disable to take full effect.
    """
    logger.info("Disabling IPv6 system-wide")
    
    # Create sysctl configuration to disable IPv6
    sysctl_file = '/etc/sysctl.d/99-disable-ipv6.conf'
    try:
        with open(sysctl_file, 'w') as f:
            f.write("# Disable IPv6\n")
            f.write("net.ipv6.conf.all.disable_ipv6 = 1\n")
            f.write("net.ipv6.conf.default.disable_ipv6 = 1\n")
            f.write("net.ipv6.conf.lo.disable_ipv6 = 1\n")
        logger.info("Created IPv6 disable sysctl configuration")
    except Exception as e:
        logger.error(f"Failed to create {sysctl_file}: {e}")
        return False
    
    # Remove any IPv6 enable configuration
    enable_sysctl_file = '/etc/sysctl.d/99-enable-ipv6.conf'
    if os.path.exists(enable_sysctl_file):
        try:
            os.remove(enable_sysctl_file)
            logger.info("Removed IPv6 enable sysctl configuration")
        except Exception as e:
            logger.warning(f"Failed to remove {enable_sysctl_file}: {e}")
    
    # Apply sysctl settings immediately
    try:
        cmd = ['sysctl', '-p', sysctl_file]
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"Failed to apply sysctl settings: {result.stderr}")
            return False
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error applying sysctl settings: {e}")
        return False
    
    # Disable IPv6 on all NetworkManager connections
    success = True
    try:
        # Get all connections
        cmd = ['nmcli', '-t', '-f', 'NAME', 'connection', 'show']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            connections = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            
            for connection_name in connections:
                try:
                    # Disable IPv6 for each connection
                    cmd = ['nmcli', 'connection', 'modify', connection_name, 'ipv6.method', 'disabled']
                    logger.debug(f"Running command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode != 0:
                        logger.warning(f"Failed to disable IPv6 on connection {connection_name}: {result.stderr}")
                        success = False
                    else:
                        logger.debug(f"Disabled IPv6 on connection {connection_name}")
                except Exception as e:
                    logger.warning(f"Error disabling IPv6 on connection {connection_name}: {e}")
                    success = False
        else:
            logger.warning("Failed to get NetworkManager connections")
            success = False
            
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Error configuring NetworkManager connections: {e}")
        success = False
    
    # Add IPv6 disable to kernel parameters for complete disable
    try:
        cmdline = CmdlineTxt()
        cmdline.disable_ipv6()
        cmdline.save()
        logger.info("Updated kernel command line to disable IPv6")
        logger.info("A reboot is required for kernel-level IPv6 disable to take effect")
    except Exception as e:
        logger.warning(f"Failed to update kernel command line: {e}")
    
    # Restart NetworkManager to apply changes
    try:
        cmd = ['systemctl', 'restart', 'NetworkManager']
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"Failed to restart NetworkManager: {result.stderr}")
        else:
            logger.info("Restarted NetworkManager")
    except Exception as e:
        logger.warning(f"Error restarting NetworkManager: {e}")
    
    if success:
        logger.info("Successfully disabled IPv6 system-wide")
        return True
    else:
        logger.error("IPv6 disabled with some warnings - check logs for details")
        return False

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
    
    elif args.enable_ipv6:
        if enable_ipv6():
            logger.info("IPv6 enabled system-wide")
            sys.exit(0)
        else:
            logger.error("Failed to enable IPv6 system-wide")
            sys.exit(1)
    
    elif args.disable_ipv6:
        if disable_ipv6():
            logger.info("IPv6 disabled system-wide")
            sys.exit(0)
        else:
            logger.error("Failed to disable IPv6 system-wide")
            sys.exit(1)


def get_network_config():
    """
    Get network configuration including general information and physical interfaces.
    Returns a dictionary with hostname and interface details.
    """
    import platform
    
    # Get hostname
    hostname = platform.node()
    
    # Get physical interfaces
    interfaces = list_physical_interfaces()
    
    # Get default gateway
    default_gateway = None
    try:
        gws = netifaces.gateways()
        if 'default' in gws and netifaces.AF_INET in gws['default']:
            default_gateway = gws['default'][netifaces.AF_INET][0]
    except Exception as e:
        logger.debug(f"Could not get default gateway: {e}")
    
    # Get DNS servers
    dns_servers = []
    try:
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if line.strip().startswith('nameserver'):
                    dns = line.strip().split()[1]
                    dns_servers.append(dns)
    except Exception as e:
        logger.debug(f"Could not read DNS servers: {e}")
    
    return {
        'hostname': hostname,
        'default_gateway': default_gateway,
        'dns_servers': dns_servers,
        'interfaces': interfaces
    }


if __name__ == "__main__":
    main()
