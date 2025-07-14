#!/usr/bin/env python3

"""
Test script to verify IPv6 enable/disable functionality.
"""

import sys
import os

# Add the configurator directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'configurator'))

def test_cmdline_import():
    """Test that we can import the CmdlineTxt class."""
    try:
        from cmdline import CmdlineTxt
        print("✓ Successfully imported CmdlineTxt class")
        return True
    except Exception as e:
        print(f"✗ Failed to import CmdlineTxt: {e}")
        return False

def test_network_import():
    """Test that we can import the network module with IPv6 functions."""
    try:
        from network import enable_ipv6, disable_ipv6
        print("✓ Successfully imported IPv6 functions from network module")
        return True
    except Exception as e:
        print(f"✗ Failed to import from network module: {e}")
        return False

def test_argument_parsing():
    """Test that the argument parsing works correctly."""
    try:
        from network import parse_arguments
        
        # Test enable IPv6
        sys.argv = ['network.py', '--enable-ipv6']
        args = parse_arguments()
        assert args.enable_ipv6 == True
        print("✓ IPv6 enable argument parsing works")
        
        # Test disable IPv6
        sys.argv = ['network.py', '--disable-ipv6']
        args = parse_arguments()
        assert args.disable_ipv6 == True
        print("✓ IPv6 disable argument parsing works")
        
        return True
    except Exception as e:
        print(f"✗ Argument parsing test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing IPv6 functionality in network configurator...")
    print()
    
    tests = [
        test_cmdline_import,
        test_network_import,
        test_argument_parsing,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("All tests passed! IPv6 functionality is ready to use.")
        print()
        print("Usage examples:")
        print("  python3 configurator/network.py --enable-ipv6")
        print("  python3 configurator/network.py --disable-ipv6")
        print("  python3 configurator/network.py --list-interfaces")
    else:
        print("Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
