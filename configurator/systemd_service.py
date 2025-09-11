#!/usr/bin/env python3
"""
SystemD Service Management Tool

A tool for managing systemd services - enable, disable, start, stop, restart, and get status.
"""

import subprocess
import logging
import argparse
import sys
import json
import os
import pwd
from typing import Dict, List, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class SystemdServiceManager:
    """Manager for systemd service operations (supports system + user services)."""
    
    def __init__(self):
        """Initialize the SystemD service manager"""
        self.systemctl_cmd = "systemctl"
        # User service detection (parsed once from /etc/hifiberry.user)
        self.user_name = None
        self.user_uid = None
        self.user_runtime_dir = None
        self._detect_user_service_user()
        
        # Service environment mapping (service_name -> 'system' or 'user')
        self.service_environments = {}
        self._build_service_environment_map()
    
    def _run_command(self, command: List[str], env: Optional[Dict[str, str]] = None) -> Tuple[bool, str, str]:
        """
        Run a systemctl command and return success status, stdout, and stderr
        
        Args:
            command: List of command parts to execute
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,  # Don't raise exception on non-zero exit
                env=env if env is not None else os.environ.copy()
            )
            
            success = result.returncode == 0
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            
            logger.debug(f"Command: {' '.join(command)}")
            logger.debug(f"Return code: {result.returncode}")
            logger.debug(f"stdout: {stdout}")
            logger.debug(f"stderr: {stderr}")
            
            return success, stdout, stderr
            
        except Exception as e:
            logger.error(f"Error running command {' '.join(command)}: {e}")
            return False, "", str(e)
    
    def _detect_user_service_user(self):
        """Read /etc/hifiberry.user and set up user service context if valid.
        If file missing or user invalid, user services won't be available.
        """
        user_file = "/etc/hifiberry.user"
        try:
            if not os.path.exists(user_file):
                logger.debug(f"{user_file} does not exist, user services unavailable")
                return
            
            with open(user_file, "r") as f:
                lines = [line.strip() for line in f.readlines()]
            
            # Find first non-empty, non-comment line
            username = None
            for line in lines:
                if not line or line.startswith("#"):
                    continue
                username = line
                break
            
            if not username:
                logger.debug(f"{user_file} contains no valid username, user services unavailable")
                return
            
            # Verify user exists
            try:
                pw = pwd.getpwnam(username)
            except KeyError:
                logger.warning(f"User in {user_file} does not exist: {username}")
                return
            
            uid = pw.pw_uid
            runtime_dir = f"/run/user/{uid}"
            
            self.user_name = username
            self.user_uid = uid
            self.user_runtime_dir = runtime_dir
            
            logger.debug(f"User services available for {username} (uid={uid}, XDG_RUNTIME_DIR={runtime_dir})")
            
        except Exception as e:
            logger.warning(f"Failed to parse {user_file}: {e}")
            # User services remain unavailable
    
    def _build_service_environment_map(self):
        """Build a mapping of service names to their environment (system or user).
        This is done once at startup to determine the correct environment for each service.
        """
        self.service_environments = {}
        
        # Get system services
        try:
            system_cmd = [self.systemctl_cmd, "list-units", "--type=service", "--no-pager", "--all", "--plain", "--no-legend"]
            result = subprocess.run(system_cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 1:
                            service_name = parts[0]
                            # Remove .service suffix if present for consistency
                            if service_name.endswith('.service'):
                                service_name = service_name[:-8]
                            self.service_environments[service_name] = 'system'
        except Exception as e:
            logger.warning(f"Failed to list system services: {e}")
        
        # Get user services if user context is available
        if self.user_name and self.user_uid is not None:
            try:
                # Use systemd-run to execute user systemctl command in proper user context
                user_cmd = [
                    "systemd-run", "--uid", str(self.user_uid), "--gid", str(self.user_uid),
                    "--setenv", f"XDG_RUNTIME_DIR={self.user_runtime_dir}",
                    "--pipe", "--wait", "--quiet",
                    "systemctl", "--user", "list-units", "--type=service", "--no-pager", "--all", "--plain", "--no-legend"
                ]
                logger.debug("Listing user services with command: %s", ' '.join(user_cmd))
                result = subprocess.run(user_cmd, capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 1:
                                service_name = parts[0]
                                if service_name.endswith('.service'):
                                    service_name = service_name[:-8]
                                self.service_environments[service_name] = 'user'
                                logger.debug(f"Detected user service: {service_name}")
                else:
                    logger.debug("Failed to list user services (rc=%s): %s", result.returncode, result.stderr.strip())
            except Exception as e:
                logger.warning(f"Failed to list user services: {e}")
        
        logger.debug(f"Built service environment map with {len(self.service_environments)} services")
        if logger.isEnabledFor(logging.DEBUG):
            user_services = [name for name, env in self.service_environments.items() if env == 'user']
            if user_services:
                logger.debug(f"User services: {', '.join(user_services)}")
    
    def _get_service_environment(self, service_name):
        """Get the environment (system or user) for a given service.
        
        Args:
            service_name: Name of the service (with or without .service suffix)
            
        Returns:
            'system', 'user', or None if service not found
        """
        # Normalize service name (remove .service suffix if present)
        normalized_name = service_name
        if normalized_name.endswith('.service'):
            normalized_name = normalized_name[:-8]
        
        return self.service_environments.get(normalized_name)
    
    def _run_service_cmd(self, args: List[str], service_name: Optional[str] = None) -> Tuple[bool, str, str]:
        """Run a systemctl command in the correct environment for a service."""
        if service_name:
            env = self._get_service_environment(service_name)
            if env == 'user' and self.user_name and self.user_uid is not None:
                # User service environment - use systemd-run for proper root-to-user switching
                cmd = [
                    "systemd-run", "--uid", str(self.user_uid), "--gid", str(self.user_uid),
                    "--setenv", f"XDG_RUNTIME_DIR={self.user_runtime_dir}",
                    "--pipe", "--wait", "--quiet",
                    "systemctl", "--user"
                ] + args
                return self._run_command(cmd)
        # System (default)
        cmd = [self.systemctl_cmd] + args
        return self._run_command(cmd)
    
    def enable(self, service_name: str) -> Tuple[bool, str]:
        """
        Enable a systemd service
        
        Args:
            service_name: Name of the service to enable
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["enable", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' enabled successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to enable service '{service_name}': {error_msg}"
    
    def disable(self, service_name: str) -> Tuple[bool, str]:
        """
        Disable a systemd service
        
        Args:
            service_name: Name of the service to disable
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["disable", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' disabled successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to disable service '{service_name}': {error_msg}"
    
    def start(self, service_name: str) -> Tuple[bool, str]:
        """
        Start a systemd service
        
        Args:
            service_name: Name of the service to start
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["start", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' started successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to start service '{service_name}': {error_msg}"
    
    def stop(self, service_name: str) -> Tuple[bool, str]:
        """
        Stop a systemd service
        
        Args:
            service_name: Name of the service to stop
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["stop", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' stopped successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to stop service '{service_name}': {error_msg}"
    
    def restart(self, service_name: str) -> Tuple[bool, str]:
        """
        Restart a systemd service
        
        Args:
            service_name: Name of the service to restart
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["restart", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' restarted successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to restart service '{service_name}': {error_msg}"
    
    def reload(self, service_name: str) -> Tuple[bool, str]:
        """
        Reload a systemd service
        
        Args:
            service_name: Name of the service to reload
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_service_cmd(["reload", service_name], service_name)
        
        if success:
            return True, f"Service '{service_name}' reloaded successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to reload service '{service_name}': {error_msg}"
    
    def status(self, service_name: str) -> Tuple[bool, Dict]:
        """
        Get the status of a systemd service
        
        Args:
            service_name: Name of the service to check
            
        Returns:
            Tuple of (success, status_dict)
        """
        # Get basic status
        success, stdout, stderr = self._run_service_cmd(["status", service_name], service_name)
        
        # Get machine-readable status
        is_active_success, is_active_stdout, _ = self._run_service_cmd(["is-active", service_name], service_name)
        is_enabled_success, is_enabled_stdout, _ = self._run_service_cmd(["is-enabled", service_name], service_name)
        
        status_dict = {
            "service_name": service_name,
            "active": is_active_stdout if is_active_success else "unknown",
            "enabled": is_enabled_stdout if is_enabled_success else "unknown",
            "status_output": stdout if success else stderr,
            "status_available": success,
            "environment": self._get_service_environment(service_name) or "unknown"
        }
        
        return True, status_dict
    
    def is_active(self, service_name: str) -> bool:
        """
        Check if a service is currently active (running)
        
        Args:
            service_name: Name of the service to check
            
        Returns:
            True if service is active, False otherwise
        """
        success, stdout, _ = self._run_service_cmd(["is-active", service_name], service_name)
        return success and stdout == "active"
    
    def is_enabled(self, service_name: str) -> bool:
        """
        Check if a service is enabled (will start at boot)
        
        Args:
            service_name: Name of the service to check
            
        Returns:
            True if service is enabled, False otherwise
        """
        success, stdout, _ = self._run_service_cmd(["is-enabled", service_name], service_name)
        return success and stdout == "enabled"
    
    def list_services(self, pattern: Optional[str] = None) -> Tuple[bool, List[Dict]]:
        """
        List systemd services from both system and user environments
        
        Args:
            pattern: Optional pattern to filter services
            
        Returns:
            Tuple of (success, list_of_service_dicts)
        """
        all_services = []
        
        # Get system services
        try:
            cmd = [self.systemctl_cmd, "list-units", "--type=service", "--no-pager"]
            if pattern:
                cmd.append("--all")
            
            success, stdout, stderr = self._run_command(cmd)
            
            if success:
                services = self._parse_service_list(stdout, "system", pattern)
                all_services.extend(services)
        except Exception as e:
            logger.warning(f"Failed to list system services: {e}")
        
        # Get user services if available
        if self.user_name and self.user_uid is not None:
            try:
                cmd = [
                    "sudo", "-u", self.user_name,
                    f"XDG_RUNTIME_DIR={self.user_runtime_dir}",
                    self.systemctl_cmd, "--user", "list-units", "--type=service", "--no-pager"
                ]
                if pattern:
                    cmd.append("--all")
                
                success, stdout, stderr = self._run_command(cmd)
                
                if success:
                    services = self._parse_service_list(stdout, "user", pattern)
                    all_services.extend(services)
            except Exception as e:
                logger.warning(f"Failed to list user services: {e}")
        
        return True, all_services
    
    def _parse_service_list(self, stdout: str, environment: str, pattern: Optional[str] = None) -> List[Dict]:
        """Parse systemctl list-units output into service dictionaries"""
        services = []
        lines = stdout.split('\n')
        
        # Skip header lines and find the start of service list
        start_parsing = False
        for line in lines:
            if line.startswith('UNIT'):
                start_parsing = True
                continue
            
            if not start_parsing:
                continue
            
            # Stop at empty line or footer
            if not line.strip() or line.startswith('LOAD =') or line.startswith('●'):
                break
            
            # Parse service line
            parts = line.split()
            if len(parts) >= 4:
                service_name = parts[0]
                load_state = parts[1]
                active_state = parts[2]
                sub_state = parts[3]
                description = ' '.join(parts[4:]) if len(parts) > 4 else ""
                
                # Filter by pattern if provided
                if pattern and pattern not in service_name:
                    continue
                
                services.append({
                    "name": service_name,
                    "load": load_state,
                    "active": active_state,
                    "sub": sub_state,
                    "description": description,
                    "environment": environment
                })
        
        return services
    
    def daemon_reload(self) -> Tuple[bool, str]:
        """
        Reload systemd daemon configuration
        
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "daemon-reload"])
        
        if success:
            return True, "Systemd daemon configuration reloaded successfully"
        else:
            error_msg = stderr if stderr else stdout
            return False, f"Failed to reload systemd daemon configuration: {error_msg}"


def main():
    """Main function for command-line interface"""
    parser = argparse.ArgumentParser(description="SystemD Service Management Tool")
    
    # Logging options
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-vv", "--very-verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    # Service name
    parser.add_argument("service", nargs="?", help="Name of the service to manage")
    
    # Actions (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--enable", action="store_true", help="Enable the service")
    action_group.add_argument("--disable", action="store_true", help="Disable the service")
    action_group.add_argument("--start", action="store_true", help="Start the service")
    action_group.add_argument("--stop", action="store_true", help="Stop the service")
    action_group.add_argument("--restart", action="store_true", help="Restart the service")
    action_group.add_argument("--reload", action="store_true", help="Reload the service")
    action_group.add_argument("--status", action="store_true", help="Get service status")
    action_group.add_argument("--is-active", action="store_true", help="Check if service is active")
    action_group.add_argument("--is-enabled", action="store_true", help="Check if service is enabled")
    action_group.add_argument("--list", action="store_true", help="List services")
    action_group.add_argument("--daemon-reload", action="store_true", help="Reload systemd daemon")
    
    # List options
    parser.add_argument("--pattern", help="Pattern to filter services when listing")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.very_verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    
    # Create service manager
    manager = SystemdServiceManager()
    
    # Validate service name for actions that require it
    actions_requiring_service = [
        args.enable, args.disable, args.start, args.stop, 
        args.restart, args.reload, args.status, args.is_active, args.is_enabled
    ]
    
    if any(actions_requiring_service) and not args.service:
        print("Error: Service name is required for this action", file=sys.stderr)
        sys.exit(1)
    
    # Execute the requested action
    success = False
    result = None
    
    try:
        if args.enable:
            success, result = manager.enable(args.service)
        elif args.disable:
            success, result = manager.disable(args.service)
        elif args.start:
            success, result = manager.start(args.service)
        elif args.stop:
            success, result = manager.stop(args.service)
        elif args.restart:
            success, result = manager.restart(args.service)
        elif args.reload:
            success, result = manager.reload(args.service)
        elif args.status:
            success, result = manager.status(args.service)
        elif args.is_active:
            result = manager.is_active(args.service)
            success = True
        elif args.is_enabled:
            result = manager.is_enabled(args.service)
            success = True
        elif args.list:
            success, result = manager.list_services(args.pattern)
        elif args.daemon_reload:
            success, result = manager.daemon_reload()
        
        # Output results
        if args.json:
            if args.is_active or args.is_enabled:
                output = {"result": result, "success": success}
            elif args.status:
                output = {"success": success, "status": result}
            elif args.list:
                output = {"success": success, "services": result}
            else:
                output = {"success": success, "message": result}
            
            print(json.dumps(output, indent=2))
        else:
            if args.is_active:
                print("active" if result else "inactive")
            elif args.is_enabled:
                print("enabled" if result else "disabled")
            elif args.status:
                if success:
                    status_data = result
                    print(f"Service: {status_data['service_name']}")
                    print(f"Active: {status_data['active']}")
                    print(f"Enabled: {status_data['enabled']}")
                    if status_data['status_available']:
                        print(f"Status Output:\n{status_data['status_output']}")
                else:
                    print(f"Failed to get status: {result}")
            elif args.list:
                if success:
                    if result:
                        print(f"{'NAME':<30} {'LOAD':<10} {'ACTIVE':<10} {'SUB':<10} {'DESCRIPTION'}")
                        print("-" * 80)
                        for service in result:
                            print(f"{service['name']:<30} {service['load']:<10} {service['active']:<10} {service['sub']:<10} {service['description']}")
                    else:
                        print("No services found")
                else:
                    print("Failed to list services")
            else:
                print(result)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("Operation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
