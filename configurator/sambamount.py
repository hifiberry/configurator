#!/usr/bin/env python3

import os
import sys
import csv
import argparse
import logging
import shutil
import subprocess
from tempfile import NamedTemporaryFile
from typing import List, Dict, Optional, Tuple, Any
from configurator.configdb import ConfigDB

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
    parser = argparse.ArgumentParser(description='SMB Mount Management Tool')

    # Command group
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument('--add-mount', action='store_true', 
                        help='Add a mount configuration to the config database')
    command_group.add_argument('--remove-mount', action='store_true',
                        help='Remove a mount configuration from the config database and unmount if active')
    command_group.add_argument('--mount-all', action='store_true',
                        help='Mount all shares defined in the config database')
    command_group.add_argument('--mount', action='store_true',
                        help='Mount a specific share (requires --id OR --server and --share)')
    command_group.add_argument('--unmount', action='store_true',
                        help='Unmount a specific share (requires --id OR --server and --share)')
    command_group.add_argument('--list-mounts', action='store_true',
                        help='List all configured mounts')
    command_group.add_argument('--list-mounted-dirs', action='store_true',
                        help='List only directories that are currently mounted (one per line)')

    # Mount configuration options
    parser.add_argument('--server', help='Server name or IP address (for mount operations)')
    parser.add_argument('--share', help='Share name (for mount operations)')
    parser.add_argument('--user', help='Username for connection')
    parser.add_argument('--password', help='Password for connection')
    parser.add_argument('--mountpoint', help='Mount point (default: /data/server-share)')
    parser.add_argument('--version', choices=['SMB1', 'SMB2', 'SMB3'], 
                        help='SMB protocol version to use')
    parser.add_argument('--mount-options', default='',
                        help='Additional mount options for CIFS mounts')

    # Create mutually exclusive group for verbosity control
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    verbosity_group.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress all output except warnings and errors')

    return parser.parse_args()

def read_mount_config(secure: bool = False) -> List[Dict[str, str]]:
    """
    Read the mount configurations from the config database.

    Args:
        secure: If True, read the password in secure mode.

    Returns:
        List of dictionaries, each containing a mount configuration
    """
    db = ConfigDB()
    mounts = []
    index = 1

    while True:
        prefix = f"smbmount.{index}"
        server = db.get(f"{prefix}.server", None)
        if not server:
            break

        share = db.get(f"{prefix}.share", "")
        mountpoint = db.get(f"{prefix}.mountpoint", "")
        user = db.get(f"{prefix}.user", "")
        password = db.get(f"{prefix}.password", secure=secure)  # Use the secure argument here
        version = db.get(f"{prefix}.version", "")
        options = db.get(f"{prefix}.options", "")

        mounts.append({
            'id': index,
            'server': server,
            'share': share,
            'mountpoint': mountpoint,
            'user': user,
            'password': password,
            'version': version,
            'options': options
        })

        index += 1

    logger.debug(f"Read {len(mounts)} mount configurations from configdb")
    return mounts

def write_mount_config(mounts: List[Dict[str, str]]) -> bool:
    """
    Write the mount configurations to the config database.

    Args:
        mounts: List of dictionaries, each containing a mount configuration

    Returns:
        True if successful, False otherwise
    """
    try:
        db = ConfigDB()

        # Clear existing configurations
        index = 1
        while db.get(f"smbmount.{index}.server", None):
            prefix = f"smbmount.{index}"
            db.delete(f"{prefix}.server")
            db.delete(f"{prefix}.share")
            db.delete(f"{prefix}.mountpoint")
            db.delete(f"{prefix}.user")
            db.delete(f"{prefix}.password")
            db.delete(f"{prefix}.version")
            db.delete(f"{prefix}.options")
            index += 1

        # Write new configurations
        for i, mount in enumerate(mounts, start=1):
            prefix = f"smbmount.{i}"
            db.set(f"{prefix}.server", mount['server'])
            db.set(f"{prefix}.share", mount['share'])
            db.set(f"{prefix}.mountpoint", mount['mountpoint'])
            db.set(f"{prefix}.user", mount['user'])
            db.set(f"{prefix}.password", mount['password'], secure=True)  # Encrypt password
            db.set(f"{prefix}.version", mount['version'])
            db.set(f"{prefix}.options", mount['options'])

        logger.debug(f"Wrote {len(mounts)} mount configurations to configdb")
        return True
    except Exception as e:
        logger.error(f"Error writing mount configurations to configdb: {e}")
        return False

def add_mount_config(server: str, share: str, mountpoint: Optional[str] = None,
                    user: Optional[str] = None, password: Optional[str] = None,
                    version: Optional[str] = None, options: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Add a mount configuration to the configuration database.
    
    Args:
        server: Server name or IP address
        share: Share name
        mountpoint: Mount point (default: /data/server-share)
        user: Username for connection
        password: Password for connection
        version: SMB protocol version
        options: Additional mount options
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    # Read existing configurations
    mounts = read_mount_config(secure=True)
    
    # Generate default mountpoint if not specified
    if not mountpoint:
        mountpoint = f"/data/{server}-{share}"
    
    # Check if configuration already exists
    for mount in mounts:
        if mount['server'] == server and mount['share'] == share:
            error_msg = f"Mount configuration for {server}/{share} already exists"
            logger.error(error_msg)
            return False, error_msg
    
    # Create new configuration
    new_mount = {
        'server': server,
        'share': share,
        'mountpoint': mountpoint,
        'user': user or '',
        'password': password or '',
        'version': version or '',
        'options': options or ''
    }
    
    # Add to list
    mounts.append(new_mount)
    
    # Write the new mount configuration directly to the database
    try:
        db = ConfigDB()
        
        # Find the next available ID by checking which slots are free
        next_id = 1
        while db.get(f"smbmount.{next_id}.server", None) is not None:
            next_id += 1
        
        prefix = f"smbmount.{next_id}"
        
        # Write the new mount configuration directly
        db.set(f"{prefix}.server", new_mount['server'])
        db.set(f"{prefix}.share", new_mount['share'])
        db.set(f"{prefix}.mountpoint", new_mount['mountpoint'])
        db.set(f"{prefix}.user", new_mount['user'])
        db.set(f"{prefix}.password", new_mount['password'], secure=True)  # Encrypt password
        db.set(f"{prefix}.version", new_mount['version'])
        db.set(f"{prefix}.options", new_mount['options'])
        
        logger.debug(f"Added mount configuration {next_id} for {server}/{share} to configdb")
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to save mount configuration for {server}/{share}: {e}"
        logger.error(error_msg)
        return False, error_msg

def remove_mount_config(server: str, share: str) -> Tuple[bool, Optional[str]]:
    """
    Remove a mount configuration from the configuration database.
    
    Args:
        server: Server name or IP address
        share: Share name
        
    Returns:
        Tuple of (True if successful, mountpoint if unmounted, or None)
    """
    # Read existing configurations
    mounts = read_mount_config(secure=True)
    mountpoint = None
    
    # Find the configuration to remove
    new_mounts = []
    found = False
    
    for mount in mounts:
        if mount['server'] == server and mount['share'] == share:
            found = True
            mountpoint = mount['mountpoint']
        else:
            new_mounts.append(mount)
    
    if not found:
        logger.error(f"Mount configuration for {server}/{share} not found")
        return False, None
    
    # Note: We don't automatically unmount here since the systemd service handles mounting/unmounting
    logger.debug(f"Removing mount configuration for {server}/{share} from configdb (mountpoint: {mountpoint})")
    
    # Write back to database
    success = write_mount_config(new_mounts)
    return success, mountpoint

def is_mounted(mountpoint: str) -> bool:
    """
    Check if a mountpoint is mounted by reading /proc/mounts.
    
    Args:
        mountpoint: Path to the mountpoint
        
    Returns:
        True if mounted, False otherwise
    """
    if not mountpoint:
        return False
        
    try:
        # Normalize the mountpoint path
        normalized_mountpoint = os.path.abspath(mountpoint)
        logger.debug(f"Checking mount status for: {mountpoint} (normalized: {normalized_mountpoint})")
        
        # Check /proc/mounts for exact mountpoint match
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    # Split the line: device mountpoint filesystem options
                    logging.debug(f"/proc/mounts: {line.strip()}")
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        device = parts[0]
                        mount_path = parts[1]
                        filesystem = parts[2]
                        
                        # Compare normalized paths
                        normalized_mount_path = os.path.abspath(mount_path)
                        if normalized_mount_path == normalized_mountpoint:
                            logger.debug(f"Found active mount: {device} -> {mount_path} ({filesystem})")
                            return True
                            
        except Exception as proc_error:
            logger.debug(f"Error reading /proc/mounts: {proc_error}")
        
        logger.debug(f"No active mount found for: {mountpoint}")
        return False
        
    except Exception as e:
        logger.debug(f"Error checking mount status for {mountpoint}: {e}")
        return False

def mount_cifs_share(server: str, share: str, mountpoint: str, username: Optional[str] = None,
                    password: Optional[str] = None, version: Optional[str] = None,
                    options: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Mount a CIFS share.
    
    Args:
        server: Server name or IP address
        share: Share name
        mountpoint: Mount point
        username: Username for connection
        password: Password for connection
        version: SMB protocol version
        options: Additional mount options
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    # Check if mount command is available
    if not shutil.which('mount'):
        error_msg = "mount command not found"
        logger.error(error_msg)
        return False, error_msg
    
    # Create mountpoint if it doesn't exist
    if not os.path.exists(mountpoint):
        try:
            os.makedirs(mountpoint, exist_ok=True)
        except Exception as e:
            error_msg = f"Error creating mountpoint {mountpoint}: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    # Check if already mounted
    if is_mounted(mountpoint):
        logger.info(f"{mountpoint} is already mounted")
        return True, None
    
    # Build mount options
    mount_opts = []
    
    # Add credentials if provided
    if username:
        mount_opts.append(f"username={username}")
    if password:
        mount_opts.append(f"password={password}")
    
    # Add SMB version if specified
    if version:
        if version == "SMB1":
            mount_opts.append("vers=1.0")
        elif version == "SMB2":
            mount_opts.append("vers=2.1")
        elif version == "SMB3":
            mount_opts.append("vers=3.0")
    
    # Add additional options
    if options:
        mount_opts.extend(options.split(','))
    
    # Create the mount command
    cmd = ['mount', '-t', 'cifs', f'//{server}/{share}', mountpoint, '-o', ','.join(mount_opts)]
    
    # Log the command without the password
    safe_cmd = cmd.copy()
    for i, opt in enumerate(safe_cmd):
        if 'password=' in opt:
            safe_cmd[i] = 'password=****'
    logger.debug(f"Running command: {' '.join(safe_cmd)}")
    
    try:
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"Successfully mounted {server}/{share} at {mountpoint}")
            return True, None
        else:
            # Parse the error output to provide more specific error information
            stderr_output = result.stderr.strip()
            stdout_output = result.stdout.strip()
            
            # Log detailed error information
            logger.error(f"Mount command failed for {server}/{share} -> {mountpoint}")
            logger.error(f"Mount command return code: {result.returncode}")
            if stderr_output:
                logger.error(f"Mount stderr: {stderr_output}")
            if stdout_output:
                logger.error(f"Mount stdout: {stdout_output}")
            
            # Analyze common error patterns and provide helpful information
            error_lower = stderr_output.lower()
            if "permission denied" in error_lower or "access denied" in error_lower:
                logger.error(f"Authentication failed for {server}/{share} - check username/password")
                error_msg = f"Authentication failed for {server}/{share}: {stderr_output}"
            elif "no such file or directory" in error_lower or "not found" in error_lower:
                logger.error(f"Share {share} not found on server {server}")
                error_msg = f"Share not found: {server}/{share}: {stderr_output}"
            elif "network is unreachable" in error_lower or "no route to host" in error_lower:
                logger.error(f"Network connection failed to server {server}")
                error_msg = f"Network connection failed to {server}: {stderr_output}"
            elif "connection refused" in error_lower or "connection timed out" in error_lower:
                logger.error(f"SMB service unavailable on server {server}")
                error_msg = f"SMB service unavailable on {server}: {stderr_output}"
            elif "mount error(13)" in stderr_output:
                logger.error(f"Permission denied mounting {server}/{share} - check credentials and share permissions")
                error_msg = f"Permission denied: {stderr_output}"
            elif "mount error(2)" in stderr_output:
                logger.error(f"Share {share} does not exist on server {server}")
                error_msg = f"Share does not exist: {stderr_output}"
            elif "mount error(112)" in stderr_output:
                logger.error(f"Host {server} is down or unreachable")
                error_msg = f"Host unreachable: {stderr_output}"
            elif "mount error(115)" in stderr_output:
                logger.error(f"Operation timed out connecting to {server}")
                error_msg = f"Connection timeout: {stderr_output}"
            else:
                logger.error(f"Unknown mount error for {server}/{share}: {stderr_output}")
                error_msg = f"Mount failed: {stderr_output}"
            
            return False, error_msg
    
    except subprocess.TimeoutExpired:
        error_msg = f"Mount operation timed out after 30 seconds for {server}/{share}"
        logger.error(error_msg)
        logger.error(f"Mount command may be hanging - check network connectivity to {server}")
        return False, error_msg
    except subprocess.SubprocessError as e:
        error_msg = f"Subprocess error while mounting {server}/{share}: {e}"
        logger.error(error_msg)
        logger.error(f"Failed to execute mount command for {server}/{share}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error while mounting {server}/{share}: {e}"
        logger.error(error_msg)
        logger.exception(f"Unexpected exception during mount operation for {server}/{share}")
        return False, error_msg
    
    return False, "Unknown error occurred during mount operation"

def unmount_share(mountpoint: str, lazy_fallback: bool = False) -> tuple[bool, Optional[str]]:
    """
    Unmount a share.
    
    Args:
        mountpoint: Path to the mountpoint
        lazy_fallback: If True, attempt lazy unmount as fallback when normal unmount fails
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    # Check if umount command is available
    if not shutil.which('umount'):
        error_msg = "umount command not found"
        logger.error(error_msg)
        return False, error_msg
    
    # Check if mounted
    if not is_mounted(mountpoint):
        logger.info(f"{mountpoint} is not mounted")
        return True, None
    
    # Unmount the share
    cmd = ['umount', mountpoint]
    logger.debug(f"Running command: {' '.join(cmd)}")
    
    try:
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"Successfully unmounted {mountpoint}")
            return True, None
        else:
            # Parse the error output to provide more specific error information
            stderr_output = result.stderr.strip()
            stdout_output = result.stdout.strip()
            
            # Log detailed error information
            logger.error(f"Unmount command failed for {mountpoint}")
            logger.error(f"Unmount command return code: {result.returncode}")
            if stderr_output:
                logger.error(f"Unmount stderr: {stderr_output}")
            if stdout_output:
                logger.error(f"Unmount stdout: {stdout_output}")
            
            # Analyze common unmount error patterns
            error_lower = stderr_output.lower()
            if "target is busy" in error_lower or "device is busy" in error_lower:
                logger.error(f"Mountpoint {mountpoint} is busy - files or processes may be using it")
                error_msg = f"Device busy: {stderr_output}"
            elif "not mounted" in error_lower or "not found" in error_lower:
                logger.warning(f"Mountpoint {mountpoint} is not currently mounted")
                error_msg = f"Not mounted: {stderr_output}"
            elif "permission denied" in error_lower:
                logger.error(f"Permission denied unmounting {mountpoint} - check privileges")
                error_msg = f"Permission denied: {stderr_output}"
            else:
                logger.error(f"Unknown unmount error for {mountpoint}: {stderr_output}")
                error_msg = f"Unmount failed: {stderr_output}"
            
            # If normal unmount fails, try lazy unmount as fallback (only if enabled)
            if lazy_fallback and ("target is busy" in error_lower or "device is busy" in error_lower):
                logger.warning(f"Mount point busy, attempting lazy unmount for {mountpoint}")
                lazy_cmd = ['umount', '-l', mountpoint]  # -l for lazy unmount
                logger.debug(f"Running lazy unmount: {' '.join(lazy_cmd)}")
                
                try:
                    lazy_result = subprocess.run(lazy_cmd, capture_output=True, text=True, timeout=10)
                    if lazy_result.returncode == 0:
                        logger.info(f"Successfully performed lazy unmount of {mountpoint}")
                        return True, None
                    else:
                        lazy_stderr = lazy_result.stderr.strip()
                        logger.error(f"Lazy unmount also failed for {mountpoint}")
                        logger.error(f"Lazy unmount stderr: {lazy_stderr}")
                        error_msg = f"Lazy unmount also failed: {lazy_stderr}"
                        return False, error_msg
                except Exception as e:
                    logger.error(f"Exception during lazy unmount of {mountpoint}: {e}")
                    return False, f"Lazy unmount exception: {e}"
            
            return False, error_msg
    
    except subprocess.TimeoutExpired:
        error_msg = f"Unmount operation timed out after 10 seconds for {mountpoint}"
        logger.error(error_msg)
        logger.error(f"Unmount command may be hanging for {mountpoint} - the mountpoint may be busy")
        return False, error_msg
    except subprocess.SubprocessError as e:
        error_msg = f"Subprocess error while unmounting {mountpoint}: {e}"
        logger.error(error_msg)
        logger.error(f"Failed to execute unmount command for {mountpoint}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error while unmounting {mountpoint}: {e}"
        logger.error(error_msg)
        logger.exception(f"Unexpected exception during unmount operation for {mountpoint}")
        return False, error_msg
    
    return False, "Unknown error occurred during unmount operation"

def mount_all_shares() -> Dict[str, Any]:
    """
    Mount all shares defined in the configuration database.

    Returns:
        Dictionary with results: {"succeeded": List[str], "failed": List[str]}
    """
    results = {"succeeded": [], "failed": []}

    # Read mount configurations
    mounts = read_mount_config(secure=True)

    if not mounts:
        logger.info("No mount configurations found in configdb")
        return results  # Do not treat this as an error

    # Mount each share
    for mount in mounts:
        server = mount['server']
        share = mount['share']
        mountpoint = mount['mountpoint']
        user = mount['user'] if 'user' in mount and mount['user'] else None
        password = mount['password'] if 'password' in mount and mount['password'] else None
        version = mount['version'] if 'version' in mount and mount['version'] else None
        options = mount['options'] if 'options' in mount and mount['options'] else None

        logger.info(f"Mounting {server}/{share} at {mountpoint}")
        mount_success, error_msg = mount_cifs_share(server, share, mountpoint, user, password, version, options)
        if mount_success:
            logger.info(f"Successfully mounted {server}/{share} at {mountpoint}")
            results["succeeded"].append(f"{server}/{share} at {mountpoint}")
        else:
            logger.error(f"Failed to mount {server}/{share} at {mountpoint}: {error_msg}")
            error_detail = f"{server}/{share} at {mountpoint}: {error_msg}" if error_msg else f"{server}/{share} at {mountpoint}"
            results["failed"].append(error_detail)

    return results

def find_mount_by_server_share(server: str, share: str) -> Optional[Dict[str, Any]]:
    """
    Find a mount configuration by server and share name.
    
    Args:
        server: Server name or IP address
        share: Share name
        
    Returns:
        Mount configuration dictionary or None if not found
    """
    mounts = read_mount_config(secure=True)
    for mount in mounts:
        if mount['server'] == server and mount['share'] == share:
            return mount
    return None

def mount_smb_share(server: str, share: str) -> bool:
    """
    Mount a specific SMB share by server and share name.
    This function looks up the configuration and mounts the share with verification.
    
    Args:
        server: Server name or IP address
        share: Share name
        
    Returns:
        True if successfully mounted and verified, False otherwise
    """
    try:
        # Find the mount configuration by server and share
        target_mount = find_mount_by_server_share(server, share)
        
        if not target_mount:
            logger.error(f"Mount configuration for {server}/{share} not found")
            return False
        
        mountpoint = target_mount['mountpoint']
        user = target_mount['user'] if target_mount['user'] else None
        password = target_mount['password'] if target_mount['password'] else None
        version = target_mount['version'] if target_mount['version'] else None
        options = target_mount['options'] if target_mount['options'] else None
        
        logger.info(f"Attempting to mount {server}/{share} at {mountpoint}")
        
        # Check if already mounted
        if is_mounted(mountpoint):
            logger.info(f"{server}/{share} is already mounted at {mountpoint}")
            return True
        
        # Attempt to mount
        mount_success, error_msg = mount_cifs_share(server, share, mountpoint, user, password, version, options)
        
        if not mount_success:
            logger.error(f"Mount operation failed for {server}/{share} -> {mountpoint}")
            logger.error(f"Mount failure reason: {error_msg}")
            return False
        
        # Verify the mount succeeded by checking again
        if is_mounted(mountpoint):
            logger.info(f"Successfully mounted and verified {server}/{share} at {mountpoint}")
            return True
        else:
            logger.error(f"Mount command succeeded but verification failed for {server}/{share}")
            logger.error(f"Mountpoint {mountpoint} is not showing as mounted after successful mount command")
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error mounting {server}/{share}: {e}")
        logger.exception(f"Exception occurred while mounting {server}/{share}")
        return False

def unmount_smb_share(server: str, share: str) -> bool:
    """
    Unmount a specific SMB share by server and share name.
    This function looks up the configuration and unmounts the share with verification.
    
    Args:
        server: Server name or IP address
        share: Share name
        
    Returns:
        True if successfully unmounted and verified, False otherwise
    """
    try:
        # Find the mount configuration by server and share
        target_mount = find_mount_by_server_share(server, share)
        
        if not target_mount:
            logger.error(f"Mount configuration for {server}/{share} not found")
            return False
        
        mountpoint = target_mount['mountpoint']
        
        logger.info(f"Attempting to unmount {server}/{share} from {mountpoint}")
        
        # Check if actually mounted
        if not is_mounted(mountpoint):
            logger.info(f"{server}/{share} is not mounted at {mountpoint}")
            return True
        
        # Attempt to unmount
        unmount_success, error_msg = unmount_share(mountpoint, lazy_fallback=True)  # Enable lazy fallback for command-line usage
        
        if unmount_success:
            logger.info(f"Successfully unmounted {server}/{share} from {mountpoint}")
            return True
        else:
            logger.error(f"Unmount operation failed for {server}/{share} from {mountpoint}")
            logger.error(f"Unmount failure reason: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error unmounting {server}/{share}: {e}")
        logger.exception(f"Exception occurred while unmounting {server}/{share}")
        return False

def list_configured_mounts() -> List[Dict[str, str]]:
    """
    List all mounts from the configuration database.
    
    Returns:
        List of mount configurations with mount status included
    """
    # Read mount configurations
    mounts = read_mount_config()
    
    if not mounts:
        logger.debug("No mount configurations found in configdb")
        return mounts
    
    # Check mount status for each mount
    for mount in mounts:
        mountpoint = mount.get('mountpoint', '')
        mount['mounted'] = is_mounted(mountpoint) if mountpoint else False
    
    return mounts

def main():
    """Main function to run when script is executed directly."""
    args = parse_arguments()
    
    # Configure logging based on verbosity
    # For --list-mounted-dirs, force quiet mode to ensure clean output
    if hasattr(args, 'list_mounted_dirs') and args.list_mounted_dirs:
        setup_logging(verbose=False, quiet=True)
    else:
        setup_logging(args.verbose, args.quiet)
    
    if args.add_mount:
        # Check required arguments
        if not args.server or not args.share:
            logger.error("--add-mount requires --server and --share")
            sys.exit(1)
        
        # Add mount configuration
        success, error_msg = add_mount_config(
            args.server, 
            args.share, 
            args.mountpoint,
            args.user,
            args.password,
            args.version,
            args.mount_options
        )
        
        if success:
            logger.info(f"Successfully added mount configuration for {args.server}/{args.share}")
            sys.exit(0)
        else:
            logger.error(f"Failed to add mount configuration for {args.server}/{args.share}: {error_msg}")
            sys.exit(1)
    
    elif args.remove_mount:
        # Check required arguments
        if not args.server or not args.share:
            logger.error("--remove-mount requires --server and --share")
            sys.exit(1)
        
        # Remove mount configuration
        success, mountpoint = remove_mount_config(args.server, args.share)
        
        if success:
            logger.info(f"Successfully removed mount configuration for {args.server}/{args.share}")
            if mountpoint:
                logger.info(f"Share was unmounted from {mountpoint}")
            sys.exit(0)
        else:
            logger.error(f"Failed to remove mount configuration for {args.server}/{args.share}")
            sys.exit(1)
    
    elif args.mount_all:
        # Mount all shares
        results = mount_all_shares()
        
        # Report results
        if results["succeeded"]:
            logger.info(f"Successfully mounted {len(results['succeeded'])} shares:")
            for mount in results["succeeded"]:
                logger.info(f"  - {mount}")
        
        if results["failed"]:
            logger.error(f"Failed to mount {len(results['failed'])} shares:")
            for mount in results["failed"]:
                logger.error(f"  - {mount}")
            # Exit with error if any mounts failed
            sys.exit(1)
        
        # Exit with success if at least one mount succeeded
        if results["succeeded"]:
            sys.exit(0)
        else:
            logger.warning("No shares were mounted")
            sys.exit(0)
    
    elif args.mount:
        # Mount a specific share
        if args.server and args.share:
            # Mount by server/share
            success = mount_smb_share(args.server, args.share)
            if success:
                logger.info(f"Successfully mounted {args.server}/{args.share}")
                sys.exit(0)
            else:
                logger.error(f"Failed to mount {args.server}/{args.share}")
                sys.exit(1)
        else:
            logger.error("--mount requires both --server and --share")
            sys.exit(1)
    
    elif args.unmount:
        # Unmount a specific share
        if args.server and args.share:
            # Unmount by server/share
            success = unmount_smb_share(args.server, args.share)
            if success:
                logger.info(f"Successfully unmounted {args.server}/{args.share}")
                sys.exit(0)
            else:
                logger.error(f"Failed to unmount {args.server}/{args.share}")
                sys.exit(1)
        else:
            logger.error("--unmount requires both --server and --share")
            sys.exit(1)
    
    elif args.list_mounts:
        # List all configured mounts
        mounts = list_configured_mounts()
        
        if mounts:
            for mount in mounts:
                mount_id = mount.get('id', '?')
                server = mount['server']
                share = mount['share']
                mountpoint = mount['mountpoint']
                user = mount['user'] if 'user' in mount and mount['user'] else ''
                version = mount['version'] if 'version' in mount and mount['version'] else 'Auto'
                password = '***' if 'password' in mount and mount['password'] else ''
                mounted = mount.get('mounted', False)
                
                # Mount status indicator
                status_icon = "✓" if mounted else "✗"
                status_text = "MOUNTED" if mounted else "UNMOUNTED"

                # Format: [ID] [STATUS] //user@server/share -> mountpoint (SMB Version)
                user_prefix = f"{user}@" if user else ""
                password_suffix = f" (Password: {password})" if password else ""
                print(f"[{mount_id}] [{status_icon} {status_text}] //{user_prefix}{server}/{share} -> {mountpoint} ({version}){password_suffix}")
        else:
            logger.warning("No mount configurations found in configdb")
    
    elif args.list_mounted_dirs:
        # List only directories that are currently mounted (one per line)
        mounts = list_configured_mounts()
        
        if mounts:
            for mount in mounts:
                mounted = mount.get('mounted', False)
                if mounted:
                    mountpoint = mount['mountpoint']
                    print(mountpoint)
        # No output if no mounted directories found

if __name__ == "__main__":
    main()
