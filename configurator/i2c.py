#!/usr/bin/env python3

import os
import logging
from typing import Dict, List

try:
    import smbus2
except ImportError:
    smbus2 = None

# Set up logging
logger = logging.getLogger(__name__)


def scan_i2c_bus(bus_number=1):
    """
    Scan I2C bus for devices and detect which addresses are in use.
    
    Args:
        bus_number: I2C bus number to scan (default: 1)
        
    Returns:
        Dictionary with detected devices and kernel-used addresses
    """
    if smbus2 is None:
        raise ImportError("smbus2 module not available. Install with: pip install smbus2")
    
    detected_devices = []
    kernel_used = []
    
    try:
        # Open I2C bus
        bus = smbus2.SMBus(bus_number)
        
        # Scan addresses 0x03 to 0x77 (standard I2C address range)
        for addr in range(0x03, 0x78):
            try:
                # Try to read a byte from the device
                bus.read_byte(addr)
                detected_devices.append(f"0x{addr:02x}")
            except OSError:
                # Device not present or not responding
                pass
        
        bus.close()
        
        # Check for kernel-used addresses by reading /sys/bus/i2c/devices/
        try:
            devices_path = f"/sys/bus/i2c/devices/i2c-{bus_number}"
            if os.path.exists(devices_path):
                for item in os.listdir(devices_path):
                    if '-' in item and item.startswith(f"{bus_number}-"):
                        # Extract address from device name (format: bus-address)
                        addr_str = item.split('-')[1]
                        if len(addr_str) >= 4:  # Should be like "0048" or "004d"
                            addr = int(addr_str, 16)
                            addr_hex = f"0x{addr:02x}"
                            if addr_hex not in kernel_used:
                                kernel_used.append(addr_hex)
        except Exception as e:
            logger.debug(f"Could not read kernel I2C devices: {e}")
        
    except Exception as e:
        logger.error(f"Error scanning I2C bus {bus_number}: {e}")
        raise
    
    return {
        'bus_number': bus_number,
        'detected_devices': sorted(detected_devices),
        'kernel_used': sorted(kernel_used),
        'scan_range': '0x03-0x77'
    }


def get_i2c_info(bus_number=1):
    """
    Get I2C bus information including device scan results.
    
    Args:
        bus_number: I2C bus number to scan (default: 1)
        
    Returns:
        Dictionary with I2C bus information and device scan results
    """
    # Check if I2C bus exists
    bus_path = f"/dev/i2c-{bus_number}"
    bus_exists = os.path.exists(bus_path)
    
    result = {
        'bus_number': bus_number,
        'bus_path': bus_path,
        'bus_exists': bus_exists,
        'smbus2_available': smbus2 is not None
    }
    
    if not bus_exists:
        result['error'] = f"I2C bus {bus_number} not found. Make sure I2C is enabled."
        return result
    
    if smbus2 is None:
        result['error'] = "smbus2 module not available. Cannot scan I2C bus."
        return result
    
    try:
        scan_result = scan_i2c_bus(bus_number)
        result.update(scan_result)
    except Exception as e:
        result['error'] = str(e)
    
    return result
