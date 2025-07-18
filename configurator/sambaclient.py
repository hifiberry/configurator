#!/usr/bin/env python3

import subprocess
import ipaddress
import netifaces
import re
import sys
import argparse
import logging
from typing import List, Dict, Optional, Tuple
import shutil
import os
from tempfile import NamedTemporaryFile

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
    
    # Create console handler that sends to stderr
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
    parser = argparse.ArgumentParser(description='SMB/CIFS client tools')
    
    # Add common authentication arguments
    parser.add_argument('-u', '--user', help='Username for authentication')
    parser.add_argument('-p', '--password', help='Password for authentication')
    parser.add_argument('-c', '--credentials', help='Path to credentials file')
    
    # Add SMB version argument
    parser.add_argument('--smbversion', choices=['SMB1', 'SMB2', 'SMB3'], 
                        help='Specify SMB version to use')
    
    # Add verbosity arguments
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress non-essential output')
    
    # Add mutually exclusive command arguments
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument('--list-file-servers', action='store_true',
                              help='List all SMB file servers on the network')
    command_group.add_argument('--check-connect', metavar='SERVER',
                              help='Test connection to specified server')
    command_group.add_argument('--detect-version', metavar='SERVER',
                              help='Detect SMB version of specified server')
    command_group.add_argument('--list-shares', metavar='SERVER',
                              help='List shares on specified server')
    
    # Add format argument for list-shares
    parser.add_argument('--long', action='store_true',
                        help='Use detailed format when listing shares')
    
    return parser.parse_args()

def get_broadcast_addresses() -> List[str]:
    """Get broadcast addresses for all active network interfaces."""
    broadcast_addresses = []
    
    for interface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(interface)
        
        # Check for IPv4 addresses
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                if 'broadcast' in addr:
                    broadcast_addresses.append(addr['broadcast'])
    
    return broadcast_addresses


def get_local_networks() -> List[Tuple[ipaddress.IPv4Network, str]]:
    """Get all directly connected networks."""
    networks = []
    
    for interface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(interface)
        
        # Check for IPv4 addresses
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                if 'addr' in addr and 'netmask' in addr:
                    ip = addr['addr']
                    netmask = addr['netmask']
                    
                    # Create network object
                    try:
                        ip_obj = ipaddress.IPv4Address(ip)
                        netmask_obj = ipaddress.IPv4Address(netmask)
                        # Calculate prefix length from netmask
                        prefix_len = bin(int(netmask_obj)).count('1')
                        network = ipaddress.IPv4Network(f"{ip}/{prefix_len}", strict=False)
                        networks.append((network, interface))
                    except (ValueError, AttributeError):
                        continue
    
    return networks


def is_on_local_network(ip: str, local_networks: List[Tuple[ipaddress.IPv4Network, str]]) -> bool:
    """Check if an IP address is on a directly connected network."""
    try:
        ip_obj = ipaddress.IPv4Address(ip)
        for network, _ in local_networks:
            if ip_obj in network:
                return True
        return False
    except ValueError:
        return False


def find_smb_servers(broadcast_address: str) -> List[Dict[str, str]]:
    """Find SMB servers using nmblookup for a specific broadcast address."""
    servers = []
    
    try:
        # Run nmblookup command
        cmd = ["nmblookup", "-B", broadcast_address, "--", "WORKGROUP"]
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # Process output lines
            for line in result.stdout.splitlines():
                # Pattern to match IP addresses followed by NetBIOS names
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+(\S+)', line)
                if match:
                    ip = match.group(1)
                    name = match.group(2)
                    # Clean up the name by removing NetBIOS suffixes like <00>
                    clean_name = re.sub(r'<[0-9a-fA-F]+>', '', name)
                    logger.debug(f"Found server: {ip} ({clean_name})")
                    servers.append({
                        'ip': ip,
                        'workgroup': clean_name,
                        'broadcast': broadcast_address
                    })
    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error querying {broadcast_address}: {e}")
    
    return servers


def is_file_server(ip_address: str) -> Optional[str]:
    """
    Check if the IP address is a file server by looking for <20> flag in nmblookup output.
    Returns the hostname if it's a file server, otherwise None.
    """
    try:
        # Run nmblookup command with -A option
        cmd = ["nmblookup", "-A", ip_address]
        logger.debug(f"Checking if {ip_address} is a file server...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            hostname = None
            is_file_service = False
            
            # First find the hostname from <00> entry
            for line in result.stdout.splitlines():
                # Look for lines containing <00> which represents the computer name
                if '<00>' in line:
                    # Extract the hostname (first word in the line)
                    parts = line.strip().split()
                    if parts:
                        hostname = parts[0]
                        logger.debug(f"Found hostname: {hostname}")
                        break
            
            # Then check for file service (<20>)
            for line in result.stdout.splitlines():
                if '<20>' in line and 'ACTIVE' in line:
                    is_file_service = True
                    logger.debug(f"{ip_address} is a file server")
                    break
            
            # Return hostname if it's a file server
            if hostname and is_file_service:
                return hostname
            elif hostname:
                logger.debug(f"{ip_address} ({hostname}) is not a file server")
            else:
                logger.debug(f"{ip_address} hostname not found")
    
    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error checking if {ip_address} is a file server: {e}")
    
    return None


def get_host_info(ip_address: str) -> Dict[str, str]:
    """Get detailed host information for an IP address using nmblookup."""
    host_info = {
        'hostname': '',
        'workgroup': '',
        'services': []
    }
    
    try:
        # Run nmblookup command with reverse lookup
        cmd = ["nmblookup", "-A", ip_address]
        logger.debug(f"Getting detailed info for {ip_address}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # Process output lines to find hostname and service info
            for line in result.stdout.splitlines():
                # Check for NetBIOS names and their service types
                match = re.search(r'(\S+)\s+<([0-9a-fA-F]+)>\s+(.+)', line)
                if match:
                    name = match.group(1)
                    # Store different types of information based on flags
                    if '<00>' in line and 'UNIQUE' in line and not host_info['hostname']:
                        host_info['hostname'] = name
                        logger.debug(f"Found hostname: {name}")
                    elif '<00>' in line and 'GROUP' in line and not host_info['workgroup']:
                        host_info['workgroup'] = name
                        logger.debug(f"Found workgroup: {name}")
                    elif '<20>' in line and 'ACTIVE' in line:  # File sharing service
                        host_info['services'].append('File Server')
                        logger.debug(f"Found file server service")
    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error querying detailed info for {ip_address}: {e}")
    
    return host_info


def list_all_servers() -> List[Dict[str, str]]:
    """List all SMB servers on the network by querying all broadcast addresses."""
    all_servers = []
    broadcast_addresses = get_broadcast_addresses()
    local_networks = get_local_networks()
    
    if not broadcast_addresses:
        logger.error("No broadcast addresses found on local interfaces.")
        return []
    
    logger.info(f"Scanning {len(broadcast_addresses)} broadcast addresses for SMB servers...")
    
    for broadcast in broadcast_addresses:
        logger.debug(f"Scanning broadcast address: {broadcast}")
        servers = find_smb_servers(broadcast)
        all_servers.extend(servers)
    
    # Remove duplicates based on IP address and filter for directly connected networks
    unique_servers = []
    seen_ips = set()
    for server in all_servers:
        if server['ip'] not in seen_ips and is_on_local_network(server['ip'], local_networks):
            seen_ips.add(server['ip'])
            
            # Add network information to server data
            for network, interface in local_networks:
                if ipaddress.IPv4Address(server['ip']) in network:
                    server['local_network'] = str(network)
                    server['interface'] = interface
                    logger.debug(f"Server {server['ip']} is on network {network} (interface {interface})")
                    break
            
            # Check if it's a file server
            file_server_hostname = is_file_server(server['ip'])
            if file_server_hostname:
                server['is_file_server'] = True
                server['hostname'] = file_server_hostname
                server['services'] = ['File Server']
                # Keep the workgroup from initial discovery if not already set
                if 'workgroup' not in server:
                    server['workgroup'] = server.get('workgroup', '')
                logger.info(f"Found file server: {server['ip']} ({file_server_hostname})")
            else:
                server['is_file_server'] = False
                
                # Get detailed host information only if it's not identified as a file server
                logger.debug(f"Querying detailed information for {server['ip']}...")
                host_info = get_host_info(server['ip'])
                server.update({
                    'hostname': host_info['hostname'],
                    'workgroup': host_info['workgroup'] or server.get('workgroup', ''),
                    'services': host_info['services']
                })
            
            unique_servers.append(server)
    
    logger.info(f"Found {len(unique_servers)} unique SMB servers on local networks.")
    return unique_servers


def check_smb_connection(server: str, username: Optional[str] = None, password: Optional[str] = None, 
                        credentials_file: Optional[str] = None) -> bool:
    """
    Check if a connection to the specified SMB server is possible with the given credentials.
    
    Args:
        server: The server address (IP or hostname)
        username: Optional username for authentication
        password: Optional password for authentication
        credentials_file: Optional path to credentials file
        
    Returns:
        bool: True if connection was successful, False otherwise
    """
    # Check if smbclient is available
    if not shutil.which('smbclient'):
        logger.error("smbclient command not found. Please install samba-client package.")
        return False
    
    # Build the command
    cmd = ['smbclient', '-L', server]
    
    # Handle authentication
    if credentials_file:
        # Use provided credentials file
        if os.path.isfile(credentials_file):
            cmd.extend(['--authentication-file', credentials_file])
        else:
            logger.error(f"Credentials file not found: {credentials_file}")
            return False
    elif username:
        cmd.extend(['-U', username])
        
        # If password is provided, use a credentials file (safer than command line)
        if password:
            # Create a temporary credentials file
            with NamedTemporaryFile(mode='w', delete=False) as cred_file:
                cred_file.write(f"username={username}\npassword={password}\n")
                cred_file_path = cred_file.name
            
            cmd.extend(['--authentication-file', cred_file_path])
    else:
        # No authentication provided, try guest/anonymous access
        cmd.append('-N')
    
    logger.debug(f"Running command: smbclient -L {server} [auth details omitted]")
    
    try:
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Clean up the temporary credentials file if it was created
        if username and password and 'cred_file_path' in locals():
            try:
                os.unlink(cred_file_path)
            except Exception as e:
                logger.debug(f"Failed to remove temporary credentials file: {e}")
        
        # Check if the command was successful
        if result.returncode == 0:
            logger.debug("Connection successful")
            logger.debug(f"Server response: {result.stdout[:200]}...")
            return True
        else:
            logger.debug(f"Connection failed with return code {result.returncode}")
            logger.debug(f"Error message: {result.stderr}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error(f"Connection to {server} timed out")
        return False
    except subprocess.SubprocessError as e:
        logger.error(f"Error connecting to {server}: {e}")
        return False
    finally:
        # Make sure to clean up the credentials file in case of exceptions
        if username and password and 'cred_file_path' in locals():
            try:
                if os.path.exists(cred_file_path):
                    os.unlink(cred_file_path)
            except Exception:
                pass
    
    return False


def list_smb_shares(server: str, username: Optional[str] = None, password: Optional[str] = None,
                   credentials_file: Optional[str] = None, smb_version: Optional[str] = None) -> Tuple[List[Dict[str, str]], str]:
    """
    List available shares on the specified SMB server.
    
    Args:
        server: The server address (IP or hostname)
        username: Optional username for authentication
        password: Optional password for authentication
        credentials_file: Optional path to credentials file
        smb_version: Optional SMB version to use
        
    Returns:
        Tuple of (list of dictionaries containing share information, detected SMB version)
    """
    shares = []
    is_share_line = False
    detected_version = "Unknown"
    
    # Check if smbclient is available
    if not shutil.which('smbclient'):
        logger.error("smbclient command not found. Please install samba-client package.")
        return shares, detected_version
    
    # SMB versions to try if not specified
    smb_versions_to_try = [smb_version] if smb_version else ["SMB3", "SMB2", "SMB1"]
    
    for version in smb_versions_to_try:
        logger.debug(f"Trying with {version}")
        
        # Build the command
        cmd = ['smbclient', '-L', server]
        
        # Add SMB version parameter
        if version == "SMB1":
            cmd.append('--option=client min protocol=NT1')
        elif version == "SMB2":
            cmd.append('--option=client min protocol=SMB2')
            cmd.append('--option=client max protocol=SMB2')
        elif version == "SMB3":
            cmd.append('--option=client min protocol=SMB3')
        
        # Handle authentication
        cred_file_path = None
        if credentials_file:
            # Use provided credentials file
            if os.path.isfile(credentials_file):
                cmd.extend(['--authentication-file', credentials_file])
            else:
                logger.error(f"Credentials file not found: {credentials_file}")
                continue
        elif username:
            cmd.extend(['-U', username])
            
            # If password is provided, use a credentials file (safer than command line)
            if password:
                # Create a temporary credentials file
                with NamedTemporaryFile(mode='w', delete=False) as cred_file:
                    cred_file.write(f"username={username}\npassword={password}\n")
                    cred_file_path = cred_file.name
                
                cmd.extend(['--authentication-file', cred_file_path])
        else:
            # No authentication provided, try guest/anonymous access
            cmd.append('-N')
        
        logger.debug(f"Running command: {' '.join(cmd).replace(server, 'SERVER')} [auth details omitted]")
        
        try:
            # Run the command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Clean up the temporary credentials file if it was created
            if cred_file_path and os.path.exists(cred_file_path):
                try:
                    os.unlink(cred_file_path)
                    cred_file_path = None  # Reset so we don't try to delete it again
                except Exception as e:
                    logger.debug(f"Failed to remove temporary credentials file: {e}")
            
            if result.returncode == 0:
                logger.debug(f"Connection successful with {version}, parsing shares")
                detected_version = version
                shares = []  # Reset shares list for each version attempt
                
                # Parse the output to extract shares
                lines = result.stdout.splitlines()
                in_share_section = False
                
                for i, line in enumerate(lines):
                    # Look for the Sharename header line
                    if "Sharename" in line and "Type" in line and "Comment" in line:
                        in_share_section = True
                        logging.debug("Found share section header")
                        # Skip the header and the separator line
                        continue
                    
                    # Check if this line is a potential share entry (starts with whitespace)
                    logging.debug(f"Processing line: {line.strip()}")
                    if line.startswith(" ") or line.startswith("\t"):
                        logging.debug("Line starts with space or tab, indicating possible share entry")
                        is_share_line = True
                    elif line and len(line) > 0:
                        # Check if the line starts with a character (not whitespace)
                        logging.debug(f"Line starts with character {line[0]} (ascii: {ord(line[0])})")
                        is_share_line = False
                    else:
                        is_share_line = False

                    if in_share_section and is_share_line:
                        # Clean up the line
                        line = line.strip()
                        
                        # Extract share name (first column)
                        parts = line.split()
                        if not parts:
                            continue
                            
                        share_name = parts[0]
                        logging.debug(f"Share name found: {share_name}")
                        
                        # Skip separator lines (all dashes)
                        if set(share_name) == {'-'}:
                            logging.debug("Skipping separator line")
                            continue
                        
                        # Skip IPC$ and admin shares
                        if share_name == "IPC$" or (share_name.endswith('$') and share_name != "IPC$"):
                            logging.debug(f"Skipping administrative share: {share_name}")
                            continue
                            
                        # Get share type if available (second column)
                        share_type = parts[1] if len(parts) > 1 else ""
                        
                        # Get comment if available (remaining columns)
                        share_comment = " ".join(parts[2:]) if len(parts) > 2 else ""
                        
                        # Add the share to our list
                        shares.append({
                            'name': share_name,
                            'type': share_type,
                            'comment': share_comment
                        })
                        logger.debug(f"Found share: {share_name}")
                    
                    # If we've already been in the share section and hit a non-indented line, we're done
                    elif in_share_section and not is_share_line:
                        in_share_section = False
                        logger.debug("Reached end of share section")
                        break
                        
                if not shares:
                    # If no shares were found but the command succeeded, log more details to help debug
                    logger.debug("No shares found in output. Output was:")
                    for line in lines:
                        logger.debug(f"  {line}")
                
                # If connection succeeded and we were able to parse the output,
                # exit the loop even if no shares were found
                # This prevents falling back to lower SMB versions unnecessarily
                if result.returncode == 0:
                    # We found a working SMB version - if we found shares or at least
                    # got a successful connection, stop trying other versions
                    if shares:
                        logger.debug(f"Found {len(shares)} shares with {version}, stopping version fallback")
                        break  # Exit the version loop if shares were found
                    else:
                        # We got a successful connection but no shares found
                        # This likely means the server doesn't have shares or user doesn't have access
                        logger.debug(f"Successful connection with {version} but no shares found")
                        # Continue checking other versions only if explicitly specified
                        if smb_version:
                            break  # User specified this version, so respect that
            else:
                logger.debug(f"Connection failed with {version}, return code {result.returncode}")
                logger.debug(f"Error message: {result.stderr}")
                # Continue to try the next version
                
        except subprocess.TimeoutExpired:
            logger.error(f"Connection to {server} with {version} timed out")
        except subprocess.SubprocessError as e:
            logger.error(f"Error connecting to {server} with {version}: {e}")
        finally:
            # Make sure to clean up the credentials file in case of exceptions
            if cred_file_path and os.path.exists(cred_file_path):
                try:
                    os.unlink(cred_file_path)
                except Exception:
                    pass
    
    return shares, detected_version


def detect_smb_version(server: str, username: Optional[str] = None, password: Optional[str] = None,
                   credentials_file: Optional[str] = None) -> str:
    """
    Detect the SMB version supported by the specified server.
    
    Args:
        server: The server address (IP or hostname)
        username: Optional username for authentication
        password: Optional password for authentication
        credentials_file: Optional path to credentials file
        
    Returns:
        String containing the detected SMB version or "Unknown"
    """
    # Check if smbclient is available
    if not shutil.which('smbclient'):
        logger.error("smbclient command not found. Please install samba-client package.")
        return "Unknown"
    
    # SMB versions to try in order of preference
    smb_versions_to_try = ["SMB3", "SMB2", "SMB1"]
    
    for version in smb_versions_to_try:
        logger.debug(f"Testing {version} compatibility with {server}")
        
        # Build the command
        cmd = ['smbclient', '-L', server]
        
        # Add SMB version parameter
        if version == "SMB1":
            cmd.append('--option=client min protocol=NT1')
        elif version == "SMB2":
            cmd.append('--option=client min protocol=SMB2')
            cmd.append('--option=client max protocol=SMB2')
        elif version == "SMB3":
            cmd.append('--option=client min protocol=SMB3')
        
        # Handle authentication
        cred_file_path = None
        if credentials_file:
            # Use provided credentials file
            if os.path.isfile(credentials_file):
                cmd.extend(['--authentication-file', credentials_file])
            else:
                logger.error(f"Credentials file not found: {credentials_file}")
                continue
        elif username:
            cmd.extend(['-U', username])
            
            # If password is provided, use a credentials file (safer than command line)
            if password:
                # Create a temporary credentials file
                with NamedTemporaryFile(mode='w', delete=False) as cred_file:
                    cred_file.write(f"username={username}\npassword={password}\n")
                    cred_file_path = cred_file.name
                
                cmd.extend(['--authentication-file', cred_file_path])
        else:
            # No authentication provided, try guest/anonymous access
            cmd.append('-N')
        
        logger.debug(f"Running command: {' '.join(cmd).replace(server, 'SERVER')} [auth details omitted]")
        
        try:
            # Run the command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Clean up the temporary credentials file if it was created
            if cred_file_path and os.path.exists(cred_file_path):
                try:
                    os.unlink(cred_file_path)
                except Exception as e:
                    logger.debug(f"Failed to remove temporary credentials file: {e}")
            
            # Check if the command was successful
            if result.returncode == 0:
                logger.debug(f"Connection successful with {version}")
                return version
            else:
                logger.debug(f"Connection failed with {version}, return code {result.returncode}")
                logger.debug(f"Error message: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            logger.error(f"Connection to {server} with {version} timed out")
        except subprocess.SubprocessError as e:
            logger.error(f"Error connecting to {server} with {version}: {e}")
        finally:
            # Make sure to clean up the credentials file in case of exceptions
            if cred_file_path and os.path.exists(cred_file_path):
                try:
                    os.unlink(cred_file_path)
                except Exception:
                    pass
    
    # If we get here, no version worked
    return "Unknown"


def main():
    """Main function to run when script is executed directly."""
    args = parse_arguments()
    
    # Configure logging based on verbosity
    setup_logging(args.verbose, args.quiet)
    
    # Check authentication parameters
    if args.password and not args.user:
        logger.error("Password provided without username (--password requires --user)")
        sys.exit(1)
    
    if args.list_file_servers:
        servers = list_all_servers()
        
        # Display only file servers with minimal information
        file_servers = [server for server in servers if server.get('is_file_server', False)]
        
        if file_servers:
            for server in file_servers:
                hostname = server['hostname'] if server['hostname'] else server.get('workgroup', '')
                print(f"{server['ip']}\t{hostname}")
        # No else clause - don't print anything if no file servers found
    
    elif args.check_connect:
        server = args.check_connect
        
        # Try connection
        result = check_smb_connection(server, args.user, args.password, args.credentials)
        
        # Output result (to stdout for potential script integration)
        if result:
            print("Connection successful")
            sys.exit(0)
        else:
            print("Connection failed")
            sys.exit(1)
    
    elif args.detect_version:
        server = args.detect_version
        
        # Detect SMB version
        version = detect_smb_version(server, args.user, args.password, args.credentials)
        
        # Print result
        print(f"SMB Version: {version}")
        
        # Exit with success if version was detected, otherwise error
        if version != "Unknown":
            sys.exit(0)
        else:
            logger.error(f"Could not detect SMB version for {server}")
            sys.exit(1)
    
    elif args.list_shares:
        server = args.list_shares
        
        # List shares with specified or auto-detected SMB version
        shares, detected_version = list_smb_shares(
            server, args.user, args.password, args.credentials, args.smbversion)
        
        if shares:
            # Print shares in the requested format (no longer printing SMB version)
            for share in shares:
                share_name = share['name']
                
                if args.long:
                    # Detailed format with comment
                    share_comment = share.get('comment', '')
                    print(f"{share_name};{share_comment}")
                else:
                    # Simple format, just the share name
                    print(share_name)
        else:
            # If no shares found or couldn't connect
            logger.warning(f"No accessible shares found on {server}")
            sys.exit(1)
    
    # Additional commands will be handled here

if __name__ == "__main__":
    main()
