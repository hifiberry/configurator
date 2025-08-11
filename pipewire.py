"""
pipewire.py - PipeWire volume control utility

Provides functions to get/set volume for a given control name and list all available volume controls.
"""
import subprocess
import json
from typing import List, Optional

def _run_pw_cli(args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(["pw-cli"] + args, capture_output=True, text=True, check=True)
        return result.stdout
    except Exception:
        return None

def get_volume_controls() -> List[str]:
    """
    Returns a list of all PipeWire volume control names.
    """
    output = _run_pw_cli(["list", "Node"])
    if not output:
        return []
    controls = []
    for line in output.splitlines():
        if "name" in line:
            # Example:    name = "alsa_output.pci-0000_00_1b.0.analog-stereo"
            parts = line.strip().split('=')
            if len(parts) == 2:
                controls.append(parts[1].strip().strip('"'))
    return controls

def get_volume(control_name: str) -> Optional[float]:
    """
    Gets the volume for the given PipeWire control name.
    Returns the volume as a float between 0.0 and 1.0, or None if not found.
    """
    output = _run_pw_cli(["info", control_name])
    if not output:
        return None
    for line in output.splitlines():
        if "volume" in line:
            # Example:    volume = 0.75
            parts = line.strip().split('=')
            if len(parts) == 2:
                try:
                    return float(parts[1].strip())
                except ValueError:
                    return None
    return None

def set_volume(control_name: str, volume: float) -> bool:
    """
    Sets the volume for the given PipeWire control name.
    Volume should be a float between 0.0 and 1.0.
    Returns True if successful, False otherwise.
    """
    try:
        subprocess.run(["pw-cli", "set", control_name, "volume", str(volume)], check=True)
        return True
    except Exception:
        return False



def main():
    import sys
    def print_usage():
        print("Usage:")
        print("  pipewire.py list")
        print("  pipewire.py get <control_name>")
        print("  pipewire.py set <control_name> <volume>")

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        controls = get_volume_controls()
        for c in controls:
            print(c)
    elif cmd == "get" and len(sys.argv) == 3:
        vol = get_volume(sys.argv[2])
        if vol is None:
            print(f"Control '{sys.argv[2]}' not found or no volume info.")
            sys.exit(2)
        print(vol)
    elif cmd == "set" and len(sys.argv) == 4:
        try:
            volume = float(sys.argv[3])
        except ValueError:
            print("Volume must be a float between 0.0 and 1.0")
            sys.exit(3)
        ok = set_volume(sys.argv[2], volume)
        if not ok:
            print(f"Failed to set volume for '{sys.argv[2]}'")
            sys.exit(4)
        print("OK")
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()

