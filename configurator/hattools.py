#!/usr/bin/env python3
import argparse
from typing import Dict, Optional

# Import from the hateeprom module in the eeprom package
try:
    from hateeprom import HatEEPROM
except ImportError:
    # Fallback if hateeprom is not available
    HatEEPROM = None

def get_hat_info() -> Dict[str, Optional[str]]:
    """
    Return a dictionary with keys 'vendor', 'product', and 'uuid'.
    If a value is not found, its value is set to None.
    
    This function now uses the hateeprom module from the eeprom package.
    """
    if HatEEPROM is None:
        print("Warning: hateeprom module not available, returning default values")
        return {"vendor": None, "product": None, "uuid": None}
    
    try:
        # Initialize HAT EEPROM interface
        hat = HatEEPROM()
        
        # Get HAT information using the short_info method
        info = hat.short_info(debug=False)
        
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
        print(f"Error reading HAT information: {e}")
        return {"vendor": None, "product": None, "uuid": None}

def main():
    parser = argparse.ArgumentParser(description="Retrieve HAT information")
    parser.add_argument("-a", "--all", action="store_true",
                        help="Display vendor, product, and UUID")
    args = parser.parse_args()

    info = get_hat_info()

    # Convert None values to default strings in main
    vendor = info["vendor"] if info["vendor"] is not None else "no vendor"
    product = info["product"] if info["product"] is not None else "no product"
    uuid = info["uuid"] if info["uuid"] is not None else "unknown"

    if args.all:
        print(f"{vendor}:{product}:{uuid}")
    else:
        print(f"{vendor}:{product}")

if __name__ == "__main__":
    main()

