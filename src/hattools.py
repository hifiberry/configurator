#!/usr/bin/env python3
"""HAT (Hardware Attached on Top) information retrieval tool.

Provides functions to read and display HAT EEPROM information including
vendor, product name, and UUID.
"""

import argparse
import logging
import sys
from typing import Dict, Optional

# Import from the hateeprom module in the eeprom package
try:
    from hateeprom import HatEEPROM  # type: ignore
except ImportError:
    # Fallback if hateeprom is not available
    HatEEPROM = None  # type: ignore

# Default values for missing HAT information
DEFAULT_VENDOR: str = "no vendor"
"""Default vendor string when vendor is not found."""
DEFAULT_PRODUCT: str = "no product"
"""Default product string when product is not found."""
DEFAULT_UUID: str = "unknown"
"""Default UUID string when UUID is not found."""

def get_hat_info(verbose: bool = False) -> Dict[str, Optional[str]]:
    """
    Return a dictionary with keys 'vendor', 'product', and 'uuid'.
    If a value is not found, its value is set to None.
    
    This function now uses the hateeprom module from the eeprom package.
    
    Args:
        verbose: If True, log warning and error messages
    """
    if HatEEPROM is None:
        if verbose:
            logging.warning("hateeprom module not available, returning default values")
        return {"vendor": None, "product": None, "uuid": None}
    
    try:
        # Initialize HAT EEPROM interface
        hat = HatEEPROM()  # type: ignore
        
        # Get HAT information using the short_info method
        info = hat.short_info(debug=False)  # type: ignore
        
        if info['success']:
            return {
                "vendor": info['vendor'] if info['vendor'] != 'Unknown' else None,
                "product": info['product'] if info['product'] != 'Unknown' else None,
                "uuid": info['uuid'] if info['uuid'] != 'Unknown' else None
            }
        else:
            # Return None values if reading failed
            return {"vendor": None, "product": None, "uuid": None}
            
    except Exception as e:
        if verbose:
            logging.error(f"Error reading HAT information: {e}")
        return {"vendor": None, "product": None, "uuid": None}

def main() -> int:
    """Retrieve and display HAT information via command-line interface.
    
    Reads HAT EEPROM data and outputs vendor, product, and UUID information.
    Supports different output formats and verbose logging.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Configure logging to send messages to stderr
    # Set to ERROR level to only show critical errors, not warnings
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    
    parser = argparse.ArgumentParser(description="Retrieve HAT information")
    parser.add_argument("-a", "--all", action="store_true",
                        help="Display vendor, product, and UUID")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose error messages")
    args = parser.parse_args()
    
    # Adjust logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.WARNING)

    info = get_hat_info(verbose=args.verbose)

    # Convert None values to default strings in main
    vendor: str = info["vendor"] if info["vendor"] is not None else DEFAULT_VENDOR
    product: str = info["product"] if info["product"] is not None else DEFAULT_PRODUCT
    uuid: str = info["uuid"] if info["uuid"] is not None else DEFAULT_UUID

    if args.all:
        print(f"{vendor}:{product}:{uuid}")
    else:
        print(f"{vendor}:{product}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

