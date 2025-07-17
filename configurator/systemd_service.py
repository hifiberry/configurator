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
from typing import Dict, List, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class SystemdServiceManager:
    """Manager for systemd service operations"""
    
    def __init__(self):
        """Initialize the SystemD service manager"""
        self.systemctl_cmd = "systemctl"
    
    def _run_command(self, command: List[str]) -> Tuple[bool, str, str]:
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
                check=False  # Don't raise exception on non-zero exit
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
    
    def enable(self, service_name: str) -> Tuple[bool, str]:
        """
        Enable a systemd service
        
        Args:
            service_name: Name of the service to enable
            
        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "enable", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "disable", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "start", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "stop", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "restart", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "reload", service_name])
        
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
        success, stdout, stderr = self._run_command([self.systemctl_cmd, "status", service_name])
        
        # Get machine-readable status
        is_active_success, is_active_stdout, _ = self._run_command([self.systemctl_cmd, "is-active", service_name])
        is_enabled_success, is_enabled_stdout, _ = self._run_command([self.systemctl_cmd, "is-enabled", service_name])
        
        status_dict = {
            "service_name": service_name,
            "active": is_active_stdout if is_active_success else "unknown",
            "enabled": is_enabled_stdout if is_enabled_success else "unknown",
            "status_output": stdout if success else stderr,
            "status_available": success
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
        success, stdout, _ = self._run_command([self.systemctl_cmd, "is-active", service_name])
        return success and stdout == "active"
    
    def is_enabled(self, service_name: str) -> bool:
        """
        Check if a service is enabled (will start at boot)
        
        Args:
            service_name: Name of the service to check
            
        Returns:
            True if service is enabled, False otherwise
        """
        success, stdout, _ = self._run_command([self.systemctl_cmd, "is-enabled", service_name])
        return success and stdout == "enabled"
    
    def list_services(self, pattern: Optional[str] = None) -> Tuple[bool, List[Dict]]:
        """
        List systemd services
        
        Args:
            pattern: Optional pattern to filter services
            
        Returns:
            Tuple of (success, list_of_service_dicts)
        """
        cmd = [self.systemctl_cmd, "list-units", "--type=service", "--no-pager"]
        if pattern:
            cmd.append(f"--all")
        
        success, stdout, stderr = self._run_command(cmd)
        
        if not success:
            return False, []
        
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
                    "description": description
                })
        
        return True, services
    
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
