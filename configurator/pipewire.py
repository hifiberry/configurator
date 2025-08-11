"""
pipewire.py - PipeWire volume control utility

Provides functions to get/set volume for a given control name and list all available volume controls.
Supports both linear (0.0-1.0) and decibel volume settings using wpctl (WirePlumber control).
"""
import subprocess
import re
import math
from typing import List, Optional, Tuple, Dict

def _run_wpctl(args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(["wpctl"] + args, capture_output=True, text=True, check=True)
        return result.stdout
    except Exception:
        return None

def _volume_to_db(volume: float) -> float:
    """
    Convert PipeWire volume (0.0-1.0) to decibels using the cubic curve that PipeWire uses.
    PipeWire uses approximately: dB ≈ 60 × log10(V) where V is the volume value.
    This is because PipeWire's volume scale follows roughly V^3 relationship to linear amplitude.
    """
    if volume <= 0:
        return -math.inf
    # PipeWire's cubic volume curve: dB ≈ 60 × log10(V)
    return 60 * math.log10(volume)

def _db_to_volume(db: float) -> float:
    """
    Convert decibel volume to PipeWire volume (0.0-1.0) using the cubic curve that PipeWire uses.
    PipeWire uses approximately: V = 10^(dB/60)
    """
    if db == -math.inf:
        return 0.0
    # PipeWire's cubic volume curve: V = 10^(dB/60)
    return 10 ** (db / 60.0)

def get_volume_controls() -> List[str]:
    """
    Returns a list of all PipeWire volume control names using wpctl.
    Format: "node_id:device_name"
    """
    output = _run_wpctl(["status"])
    if not output:
        return []
    
    controls = []
    in_audio_section = False
    in_sinks_section = False
    in_sources_section = False
    
    for line in output.splitlines():
        original_line = line
        line = line.strip()
        
        if line == "Audio":
            in_audio_section = True
            continue
        elif line == "Video" or line == "Settings":
            in_audio_section = False
            in_sinks_section = False
            in_sources_section = False
            continue
            
        if not in_audio_section:
            continue
            
        if "Sinks:" in line:
            in_sinks_section = True
            in_sources_section = False
            continue
        elif "Sources:" in line:
            in_sources_section = True
            in_sinks_section = False
            continue
        elif "Filters:" in line or "Streams:" in line:
            in_sinks_section = False
            in_sources_section = False
            continue
            
        if (in_sinks_section or in_sources_section) and line:
            # Parse lines like: " │  *   44. Built-in Audio Stereo               [vol: 0.60]"
            # Remove tree characters and asterisks
            clean_line = re.sub(r'^[│├└─\s]*\*?\s*', '', original_line)
            match = re.search(r'^(\d+)\.\s+(.+?)\s+\[', clean_line)
            if match:
                node_id = match.group(1)
                device_name = match.group(2).strip()
                controls.append(f"{node_id}:{device_name}")
    
    return controls

def get_volume(control_name: str) -> Optional[float]:
    """
    Gets the volume for the given PipeWire control name.
    Control name can be either "node_id:device_name" or just "node_id".
    Returns the volume as a float between 0.0 and 1.0, or None if not found.
    """
    # Extract node ID
    if ":" in control_name:
        node_id = control_name.split(":")[0]
    else:
        node_id = control_name
    
    try:
        output = _run_wpctl(["get-volume", node_id])
        if output:
            # Output format: "Volume: 0.60"
            match = re.search(r'Volume:\s*([\d.]+)', output)
            if match:
                return float(match.group(1))
    except Exception:
        pass
    
    return None

def get_volume_db(control_name: str) -> Optional[float]:
    """
    Gets the volume for the given PipeWire control name in decibels.
    Returns the volume in dB, or None if not found.
    """
    linear_vol = get_volume(control_name)
    if linear_vol is None:
        return None
    return _volume_to_db(linear_vol)

def set_volume(control_name: str, volume: float) -> bool:
    """
    Sets the volume for the given PipeWire control name.
    Control name can be either "node_id:device_name" or just "node_id".
    Volume should be a float between 0.0 and 1.0.
    Returns True if successful, False otherwise.
    """
    # Extract node ID
    if ":" in control_name:
        node_id = control_name.split(":")[0]
    else:
        node_id = control_name
    
    try:
        result = subprocess.run(["wpctl", "set-volume", node_id, str(volume)], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def get_default_sink() -> Optional[str]:
    """
    Returns the default sink (marked with '*' in wpctl status).
    Format: "node_id:device_name" or None if not found.
    """
    output = _run_wpctl(["status"])
    if not output:
        return None
    
    in_audio_section = False
    in_sinks_section = False
    
    for line in output.splitlines():
        original_line = line
        line = line.strip()
        
        if line == "Audio":
            in_audio_section = True
            continue
        elif line == "Video" or line == "Settings":
            in_audio_section = False
            in_sinks_section = False
            continue
            
        if not in_audio_section:
            continue
            
        if "Sinks:" in line:
            in_sinks_section = True
            continue
        elif "Sources:" in line or "Filters:" in line or "Streams:" in line:
            in_sinks_section = False
            continue
            
        if in_sinks_section and line:
            # Look for lines with asterisk: " │  *   44. Built-in Audio Stereo               [vol: 0.71]"
            if '*' in original_line:
                clean_line = re.sub(r'^[│├└─\s]*\*?\s*', '', original_line)
                match = re.search(r'^(\d+)\.\s+(.+?)\s+\[', clean_line)
                if match:
                    node_id = match.group(1)
                    device_name = match.group(2).strip()
                    return f"{node_id}:{device_name}"
    
    return None

def get_default_source() -> Optional[str]:
    """
    Returns the default source (marked with '*' in wpctl status).
    Format: "node_id:device_name" or None if not found.
    """
    output = _run_wpctl(["status"])
    if not output:
        return None
    
    in_audio_section = False
    in_sources_section = False
    
    for line in output.splitlines():
        original_line = line
        line = line.strip()
        
        if line == "Audio":
            in_audio_section = True
            continue
        elif line == "Video" or line == "Settings":
            in_audio_section = False
            in_sources_section = False
            continue
            
        if not in_audio_section:
            continue
            
        if "Sources:" in line:
            in_sources_section = True
            continue
        elif "Filters:" in line or "Streams:" in line:
            in_sources_section = False
            continue
            
        if in_sources_section and line:
            # Look for lines with asterisk
            if '*' in original_line:
                clean_line = re.sub(r'^[│├└─\s]*\*?\s*', '', original_line)
                match = re.search(r'^(\d+)\.\s+(.+?)\s+\[', clean_line)
                if match:
                    node_id = match.group(1)
                    device_name = match.group(2).strip()
                    return f"{node_id}:{device_name}"
    
    return None

def set_volume_db(control_name: str, db: float) -> bool:
    """
    Sets the volume for the given PipeWire control name in decibels.
    Returns True if successful, False otherwise.
    """
    linear_vol = _db_to_volume(db)
    return set_volume(control_name, linear_vol)

def main():
    import sys
    def print_usage():
        print("Usage:")
        print("  config-pipewire list")
        print("  config-pipewire default-sink")
        print("  config-pipewire default-source")
        print("  config-pipewire get <control_name>")
        print("  config-pipewire get-db <control_name>")
        print("  config-pipewire set <control_name> <volume>")
        print("  config-pipewire set-db <control_name> <volume_db>")
        print("")
        print("  control_name: either 'node_id:device_name' or just 'node_id'")
        print("  volume: linear volume (0.0 - 1.0)")
        print("  volume_db: volume in decibels (e.g., -20.0)")

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        controls = get_volume_controls()
        for c in controls:
            print(c)
    elif cmd == "default-sink":
        default_sink = get_default_sink()
        if default_sink:
            print(default_sink)
        else:
            print("No default sink found")
            sys.exit(2)
    elif cmd == "default-source":
        default_source = get_default_source()
        if default_source:
            print(default_source)
        else:
            print("No default source found")
            sys.exit(2)
    elif cmd == "get" and len(sys.argv) == 3:
        vol = get_volume(sys.argv[2])
        if vol is None:
            print(f"Control '{sys.argv[2]}' not found or no volume info.")
            sys.exit(2)
        print(f"{vol:.6f}")
    elif cmd == "get-db" and len(sys.argv) == 3:
        vol_db = get_volume_db(sys.argv[2])
        if vol_db is None:
            print(f"Control '{sys.argv[2]}' not found or no volume info.")
            sys.exit(2)
        if vol_db == -math.inf:
            print("-inf")
        else:
            print(f"{vol_db:.2f}")
    elif cmd == "set" and len(sys.argv) == 4:
        try:
            volume = float(sys.argv[3])
            if volume < 0.0 or volume > 1.0:
                print("Volume must be between 0.0 and 1.0")
                sys.exit(3)
        except ValueError:
            print("Volume must be a float between 0.0 and 1.0")
            sys.exit(3)
        ok = set_volume(sys.argv[2], volume)
        if not ok:
            print(f"Failed to set volume for '{sys.argv[2]}'")
            sys.exit(4)
        print("OK")
    elif cmd == "set-db" and len(sys.argv) == 4:
        try:
            volume_db = float(sys.argv[3])
        except ValueError:
            print("Volume in dB must be a float (e.g., -20.0)")
            sys.exit(3)
        ok = set_volume_db(sys.argv[2], volume_db)
        if not ok:
            print(f"Failed to set volume for '{sys.argv[2]}'")
            sys.exit(4)
        print("OK")
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
