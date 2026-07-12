#!/usr/bin/env python3
"""
HiFiBerry DSP Toolkit

Module for detecting and interacting with DSP (Digital Signal Processor) hardware
"""

import logging
import requests
import json
from typing import Optional, Dict, Any

# Default DSP service configuration
DEFAULT_DSP_HOST = "localhost"
DEFAULT_DSP_PORT = 13141
DEFAULT_TIMEOUT = 5.0

class DSPToolkit:
    """
    Toolkit for DSP hardware detection and interaction
    """
    
    def __init__(self, host: str = DEFAULT_DSP_HOST, port: int = DEFAULT_DSP_PORT, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize DSP toolkit
        
        Args:
            host: DSP service hostname (default: localhost)
            port: DSP service port (default: 13141)
            timeout: Request timeout in seconds (default: 5.0)
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
    
    def detect_dsp(self) -> Optional[Dict[str, Any]]:
        """
        Detect DSP hardware by querying the DSP service
        
        Returns:
            Dictionary with DSP detection information, or None if detection fails
            Expected format: {"detected_dsp": "ADAU14xx", "status": "detected"}
        """
        try:
            url = f"{self.base_url}/hardware/dsp"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                try:
                    dsp_info = response.json()
                    logging.debug(f"DSP detection response: {dsp_info}")
                    return dsp_info
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse DSP detection response as JSON: {e}")
                    return None
            else:
                logging.warning(f"DSP service returned status code {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            logging.debug("DSP service not available (connection refused)")
            return None
        except requests.exceptions.Timeout:
            logging.warning(f"DSP service request timed out after {self.timeout} seconds")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Error communicating with DSP service: {e}")
            return None
    
    def get_detected_dsp_name(self) -> Optional[str]:
        """
        Get the name of the detected DSP
        
        Returns:
            DSP name string if detected, None otherwise
        """
        dsp_info = self.detect_dsp()
        if dsp_info and dsp_info.get("status") == "detected":
            return dsp_info.get("detected_dsp")
        return None
    
    def is_dsp_detected(self) -> bool:
        """
        Check if a DSP is detected
        
        Returns:
            True if DSP is detected, False otherwise
        """
        dsp_info = self.detect_dsp()
        return dsp_info is not None and dsp_info.get("status") == "detected"
    
    def get_dsp_status(self) -> str:
        """
        Get the DSP detection status
        
        Returns:
            Status string ("detected", "not_detected", "error", "unavailable")
        """
        dsp_info = self.detect_dsp()
        if dsp_info is None:
            return "unavailable"
        return dsp_info.get("status", "error")

# Convenience functions for backward compatibility and ease of use
def detect_dsp(host: str = DEFAULT_DSP_HOST, port: int = DEFAULT_DSP_PORT, timeout: float = DEFAULT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Detect DSP hardware (convenience function)
    
    Args:
        host: DSP service hostname (default: localhost)
        port: DSP service port (default: 13141)  
        timeout: Request timeout in seconds (default: 5.0)
    
    Returns:
        Dictionary with DSP detection information, or None if detection fails
    """
    toolkit = DSPToolkit(host, port, timeout)
    return toolkit.detect_dsp()

def get_detected_dsp_name(host: str = DEFAULT_DSP_HOST, port: int = DEFAULT_DSP_PORT, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """
    Get the name of the detected DSP (convenience function)
    
    Args:
        host: DSP service hostname (default: localhost)
        port: DSP service port (default: 13141)
        timeout: Request timeout in seconds (default: 5.0)
    
    Returns:
        DSP name string if detected, None otherwise
    """
    toolkit = DSPToolkit(host, port, timeout)
    return toolkit.get_detected_dsp_name()

def is_dsp_detected(host: str = DEFAULT_DSP_HOST, port: int = DEFAULT_DSP_PORT, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """
    Check if a DSP is detected (convenience function)
    
    Args:
        host: DSP service hostname (default: localhost)
        port: DSP service port (default: 13141)
        timeout: Request timeout in seconds (default: 5.0)
    
    Returns:
        True if DSP is detected, False otherwise
    """
    toolkit = DSPToolkit(host, port, timeout)
    return toolkit.is_dsp_detected()

def main():
    """
    Command-line interface for DSP detection
    """
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='HiFiBerry DSP Detection Tool')
    parser.add_argument('--host', default=DEFAULT_DSP_HOST, 
                       help=f'DSP service hostname (default: {DEFAULT_DSP_HOST})')
    parser.add_argument('--port', type=int, default=DEFAULT_DSP_PORT,
                       help=f'DSP service port (default: {DEFAULT_DSP_PORT})')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                       help=f'Request timeout in seconds (default: {DEFAULT_TIMEOUT})')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    parser.add_argument('--name-only', action='store_true',
                       help='Output only the DSP name if detected')
    parser.add_argument('--status-only', action='store_true',
                       help='Output only the detection status')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
    
    # Create DSP toolkit instance
    toolkit = DSPToolkit(args.host, args.port, args.timeout)
    
    # Handle different output modes
    if args.name_only:
        dsp_name = toolkit.get_detected_dsp_name()
        if dsp_name:
            print(dsp_name)
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.status_only:
        status = toolkit.get_dsp_status()
        print(status)
        sys.exit(0 if status == "detected" else 1)
    
    elif args.json:
        dsp_info = toolkit.detect_dsp()
        if dsp_info:
            print(json.dumps(dsp_info, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({"status": "unavailable"}, indent=2))
            sys.exit(1)
    
    else:
        # Default human-readable output
        dsp_info = toolkit.detect_dsp()
        if dsp_info:
            status = dsp_info.get("status", "unknown")
            if status == "detected":
                dsp_name = dsp_info.get("detected_dsp", "Unknown")
                print(f"DSP detected: {dsp_name}")
                sys.exit(0)
            else:
                print(f"DSP status: {status}")
                sys.exit(1)
        else:
            print("DSP service unavailable")
            sys.exit(1)

if __name__ == "__main__":
    main()