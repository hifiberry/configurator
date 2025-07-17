#!/usr/bin/env python3
"""
System Information Module

Collects and provides system information from various configurator modules.
Provides both simple text output and structured data for REST API consumption.
"""

import logging
import sys
import argparse
from typing import Dict, Any, Optional

# Import from other configurator modules
from .pimodel import PiModel
from .hattools import get_hat_info

class SystemInfo:
    """Collects and provides system information from various sources"""
    
    def __init__(self):
        """Initialize the SystemInfo collector"""
        self.logger = logging.getLogger(__name__)
        self._pi_model = None
        self._hat_info = None
        self._system_uuid = None
        
    def _get_pi_model(self) -> PiModel:
        """Get Pi model information (cached)"""
        if self._pi_model is None:
            self._pi_model = PiModel()
        return self._pi_model
    
    def _get_hat_info(self) -> Dict[str, Optional[str]]:
        """Get HAT information (cached)"""
        if self._hat_info is None:
            self._hat_info = get_hat_info()
        return self._hat_info
    
    def _get_system_uuid(self) -> Optional[str]:
        """Get system UUID from /etc/uuid (cached)"""
        if self._system_uuid is None:
            try:
                with open("/etc/uuid", "r") as uuid_file:
                    self._system_uuid = uuid_file.read().strip()
            except FileNotFoundError:
                self.logger.warning("/etc/uuid file not found")
                self._system_uuid = None
            except Exception as e:
                self.logger.error(f"Failed to read /etc/uuid: {e}")
                self._system_uuid = None
        return self._system_uuid
    
    def get_pi_model_name(self) -> str:
        """Get the Pi model name"""
        try:
            pi_model = self._get_pi_model()
            return pi_model.get_model_name().strip('\x00')  # Remove null characters
        except Exception as e:
            self.logger.error(f"Failed to get Pi model: {e}")
            return "unknown"
    
    def get_hat_vendor_card(self) -> str:
        """Get HAT vendor and card name in format 'vendor:cardname'"""
        try:
            hat_info = self._get_hat_info()
            vendor = hat_info.get('vendor', 'unknown')
            product = hat_info.get('product', 'unknown')
            
            # Handle None values
            if vendor is None:
                vendor = "unknown"
            if product is None:
                product = "unknown"
                
            return f"{vendor}:{product}"
        except Exception as e:
            self.logger.error(f"Failed to get HAT info: {e}")
            return "unknown:unknown"
    
    def get_system_uuid(self) -> Optional[str]:
        """Get the system UUID from /etc/uuid"""
        try:
            return self._get_system_uuid()
        except Exception as e:
            self.logger.error(f"Failed to get system UUID: {e}")
            return None
    
    def get_system_info_dict(self) -> Dict[str, Any]:
        """Get all system information as a structured dictionary"""
        try:
            pi_model = self._get_pi_model()
            hat_info = self._get_hat_info()
            system_uuid = self._get_system_uuid()
            
            return {
                'pi_model': {
                    'name': pi_model.get_model_name().strip('\x00'),  # Remove null characters
                    'version': getattr(pi_model, 'version', 'unknown')
                },
                'hat_info': {
                    'vendor': hat_info.get('vendor'),
                    'product': hat_info.get('product'),
                    'uuid': hat_info.get('uuid'),
                    'vendor_card': self.get_hat_vendor_card()
                },
                'system': {
                    'uuid': system_uuid
                },
                'status': 'success'
            }
        except Exception as e:
            self.logger.error(f"Failed to collect system info: {e}")
            return {
                'pi_model': {
                    'name': 'unknown',
                    'version': 'unknown'
                },
                'hat_info': {
                    'vendor': None,
                    'product': None,
                    'uuid': None,
                    'vendor_card': 'unknown:unknown'
                },
                'system': {
                    'uuid': None
                },
                'status': 'error',
                'error': str(e)
            }
    
    def get_flat_info_dict(self) -> Dict[str, Any]:
        """Get all system information as a flat name-value dictionary"""
        try:
            pi_model = self._get_pi_model()
            hat_info = self._get_hat_info()
            system_uuid = self._get_system_uuid()
            
            # Build Pi Model string (name + version)
            pi_model_name = pi_model.get_model_name().strip('\x00')  # Remove null characters
            pi_version = getattr(pi_model, 'version', 'unknown')
            if pi_version != 'unknown':
                pi_model_full = f"{pi_model_name} {pi_version}"
            else:
                pi_model_full = pi_model_name
            
            # Build HAT string (vendor + product)
            vendor = hat_info.get('vendor') or 'unknown'
            product = hat_info.get('product') or 'unknown'
            hat_full = f"{vendor} {product}"
            
            flat_dict = {
                'Pi Model': pi_model_full,
                'HAT': hat_full,
                'UUID': system_uuid or 'unknown'
            }
            
            return flat_dict
        except Exception as e:
            self.logger.error(f"Failed to collect system info: {e}")
            return {
                'Pi Model': 'unknown',
                'HAT': 'unknown',
                'UUID': 'unknown'
            }
    
    def get_simple_output(self) -> str:
        """Get simple text output format"""
        pi_model_name = self.get_pi_model_name()
        hat_vendor_card = self.get_hat_vendor_card()
        system_uuid = self.get_system_uuid()
        
        output = f"Pi Model: {pi_model_name}\nHat info: {hat_vendor_card}"
        if system_uuid:
            output += f"\nSystem UUID: {system_uuid}"
        
        return output
    
    def print_simple_output(self):
        """Print the simple output to stdout"""
        print(self.get_simple_output())


def setup_logging(verbose=False):
    """Configure logging"""
    log_level = logging.DEBUG if verbose else logging.WARNING
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    root_logger.addHandler(console_handler)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='HiFiBerry System Information')
    
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON instead of simple text')
    
    return parser.parse_args()


def main():
    """Main function for command line usage"""
    args = parse_arguments()
    
    # Configure logging
    setup_logging(args.verbose)
    
    # Create system info collector
    sys_info = SystemInfo()
    
    if args.json:
        import json
        # Output as JSON with flat name-value structure
        info_dict = sys_info.get_flat_info_dict()
        print(json.dumps(info_dict, indent=2))
    else:
        # Output simple text format
        sys_info.print_simple_output()


if __name__ == "__main__":
    main()
