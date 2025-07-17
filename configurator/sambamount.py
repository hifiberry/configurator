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
    command_group.add_argument('--list-mounts', action='store_true',
                        help='List all configured mounts')

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
            db.delete(f"{prefix}.password", secure=True)
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
                    version: Optional[str] = None, options: Optional[str] = None) -> bool:
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
        True if successful, False otherwise
    """
    # Read existing configurations
    mounts = read_mount_config(secure=True)
    
    # Generate default mountpoint if not specified
    if not mountpoint:
        mountpoint = f"/data/{server}-{share}"
    
    # Check if configuration already exists
    for mount in mounts:
        if mount['server'] == server and mount['share'] == share:
            logger.error(f"Mount configuration for {server}/{share} already exists")
            return False
    
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
    
    # Write back to database
    return write_mount_config(mounts)

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
    
    # Unmount the share if it's mounted
    if mountpoint and os.path.ismount(mountpoint):
        if not unmount_share(mountpoint):
            logger.warning(f"Failed to unmount {mountpoint}")
    
    # Write back to database
    success = write_mount_config(new_mounts)
    return success, mountpoint

def is_mounted(mountpoint: str) -> bool:
    """
    Check if a mountpoint is mounted.
    
    Args:
        mountpoint: Path to the mountpoint
        
    Returns:
        True if mounted, False otherwise
    """
    try:
        with open('/proc/mounts', 'r') as f:
            for line in f:
                if mountpoint in line:
                    return True
    except Exception as e:
        logger.debug(f"Error checking mount status: {e}")
    
    return os.path.ismount(mountpoint)

def mount_cifs_share(server: str, share: str, mountpoint: str, username: Optional[str] = None,
                    password: Optional[str] = None, version: Optional[str] = None,
                    options: Optional[str] = None) -> bool:
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
        True if successful, False otherwise
    """
    # Check if mount command is available
    if not shutil.which('mount'):
        logger.error("mount command not found")
        return False
    
    # Create mountpoint if it doesn't exist
    if not os.path.exists(mountpoint):
        try:
            os.makedirs(mountpoint, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating mountpoint {mountpoint}: {e}")
            return False
    
    # Check if already mounted
    if is_mounted(mountpoint):
        logger.info(f"{mountpoint} is already mounted")
        return True
    
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
            return True
        else:
            logger.error(f"Failed to mount {server}/{share}: {result.stderr}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error(f"Mount operation timed out for {server}/{share}")
        return False
    except subprocess.SubprocessError as e:
        logger.error(f"Error mounting {server}/{share}: {e}")
        return False
    
    return False

def unmount_share(mountpoint: str) -> bool:
    """
    Unmount a share.
    
    Args:
        mountpoint: Path to the mountpoint
        
    Returns:
        True if successful, False otherwise
    """
    # Check if umount command is available
    if not shutil.which('umount'):
        logger.error("umount command not found")
        return False
    
    # Check if mounted
    if not is_mounted(mountpoint):
        logger.info(f"{mountpoint} is not mounted")
        return True
    
    # Unmount the share
    cmd = ['umount', mountpoint]
    logger.debug(f"Running command: {' '.join(cmd)}")
    
    try:
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"Successfully unmounted {mountpoint}")
            return True
        else:
            logger.error(f"Failed to unmount {mountpoint}: {result.stderr}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error(f"Unmount operation timed out for {mountpoint}")
        return False
    except subprocess.SubprocessError as e:
        logger.error(f"Error unmounting {mountpoint}: {e}")
        return False
    
    return False

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
        if mount_cifs_share(server, share, mountpoint, user, password, version, options):
            results["succeeded"].append(f"{server}/{share} at {mountpoint}")
        else:
            results["failed"].append(f"{server}/{share} at {mountpoint}")

    return results

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
    setup_logging(args.verbose, args.quiet)
    
    if args.add_mount:
        # Check required arguments
        if not args.server or not args.share:
            logger.error("--add-mount requires --server and --share")
            sys.exit(1)
        
        # Add mount configuration
        success = add_mount_config(
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
            logger.error(f"Failed to add mount configuration for {args.server}/{args.share}")
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
    
    elif args.list_mounts:
        # List all configured mounts
        mounts = list_configured_mounts()
        
        if mounts:
            for mount in mounts:
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

                # Format: [STATUS] //user@server/share -> mountpoint (SMB Version)
                user_prefix = f"{user}@" if user else ""
                password_suffix = f" (Password: {password})" if password else ""
                print(f"[{status_icon} {status_text}] //{user_prefix}{server}/{share} -> {mountpoint} ({version}){password_suffix}")
        else:
            logger.warning("No mount configurations found in configdb")

if __name__ == "__main__":
    main()
