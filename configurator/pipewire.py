"""
pipewire.py - PipeWire volume & mixer control utility

Provides functions to list controls, get/set volume (linear & dB), dump the
connection graph (pw-dot) and manipulate a custom filter-chain based mixer for
balance / mono / channel routing.

Node name assumptions for balance/mono features:
    - Virtual processing sink (what regular applications target): effect_input.proc
    - (Optional) Passive output node name: effect_output.proc
    - Parametric EQ node (single instance applying same 6 filters per channel): peq
    - Two mixer nodes used to implement balance / mono blend:
                mixer_left
                mixer_right

Expected gain parameter names exposed by PipeWire (pw-cli enum-params <mixer_id> Props):
    mixer_left:Gain 1   (Left  -> LeftOut)
    mixer_left:Gain 2   (Right -> LeftOut)
    mixer_right:Gain 1  (Left  -> RightOut)
    mixer_right:Gain 2  (Right -> RightOut)

The code here implements discrete modes (mono / stereo / left-only / right-only)
and a simple balance function B in [-1,1]. For documentation and potential
future extension, a generalized balance + mono blend model is shown below.

Generalized math (not fully implemented: current code only supports full mono M=1 or M=0):
    Given balance B in [-1,1] and mono blend M in [0,1]:
        aL = (1 - 0.5*M) * (1 - B/2)
        aR = (1 - 0.5*M) * (-B/2) + 0.5*M
        bL = (1 - 0.5*M) * (-B/2) + 0.5*M
        bR = (1 - 0.5*M) * (1 + B/2)
    Apply to mixer gains:
        mixer_left :  Gain 1 = aL   Gain 2 = aR
        mixer_right:  Gain 1 = bL   Gain 2 = bR
    Normalize gains if any |gain| > 1 by dividing all by max|gain|.

Reference filter-chain configuration (for documentation only):
-----------------------------------------------------------------
### Combined EQ (6 band) + Mono/Balance sink
# Single virtual sink so ALSA clients attach here: effect_input.proc
# Processing order: Input (stereo) -> param_eq (6 filters/channel) -> dual mixers
# Output of mixers goes directly to hardware via standard routing.

context.modules = [
    { name = libpipewire-module-filter-chain
        args = {
            node.description = "EQ + Balance Sink"
            media.name       = "EQ + Balance Sink"
            filter.graph = {
                nodes = [
                    { type = builtin label = param_eq name = peq
                        config = {
                            filters = [
                                { type = bq_lowshelf  freq = 100.0  gain = 0.0 q = 1.0 }
                                { type = bq_peaking   freq = 100.0  gain = 0.0 q = 1.0 }
                                { type = bq_peaking   freq = 500.0  gain = 0.0 q = 1.0 }
                                { type = bq_peaking   freq = 2000.0 gain = 0.0 q = 1.0 }
                                { type = bq_peaking   freq = 5000.0 gain = 0.0 q = 1.0 }
                                { type = bq_highshelf freq = 5000.0 gain = 0.0 q = 1.0 }
                            ]
                        }
                    }
                    { type = builtin label = mixer name = mixer_left  control = { "Gain 1" = 1.0 "Gain 2" = 0.0 } }
                    { type = builtin label = mixer name = mixer_right control = { "Gain 1" = 0.0 "Gain 2" = 1.0 } }
                ]
                links = [
                    { output = "peq:Out 1" input = "mixer_left:In 1" }
                    { output = "peq:Out 1" input = "mixer_right:In 1" }
                    { output = "peq:Out 2" input = "mixer_left:In 2" }
                    { output = "peq:Out 2" input = "mixer_right:In 2" }
                ]
                inputs  = [ "peq:In 1" "peq:In 2" ]
                outputs = [ "mixer_left:Out" "mixer_right:Out" ]
            }
            audio.channels = 2
            audio.position = [ FL FR ]
            capture.props = {
                node.name = "effect_input.proc"
                media.class = Audio/Sink
                node.virtual = true
                priority.session = 2000
                priority.driver = 2000
            }
            playback.props = { node.name = "effect_output.proc" node.passive = true }
        }
    }
]

context.properties = { default.audio.sink = effect_input.proc }
-----------------------------------------------------------------

This configuration is not auto-deployed by this module; it documents the
assumed topology for mixer manipulation. If your node names differ, you can
override them by extending the helper functions to accept custom names.
"""
import subprocess
import re
import math
import logging
from typing import List, Optional, Tuple, Dict, Union

logger = logging.getLogger(__name__)

# Cache for last applied mixer gains (used when PipeWire can't report them)
_last_mixer_gains: Dict[str, float] = {}

def _run_wpctl(args: List[str]) -> Optional[str]:
    try:
        logger.debug(f"Running wpctl command: wpctl {' '.join(args)}")
        result = subprocess.run(["wpctl"] + args, capture_output=True, text=True, check=True)
        logger.debug(f"wpctl stdout length: {len(result.stdout)}")
        if len(result.stdout) < 500:  # Only log short outputs to avoid spam
            logger.debug(f"wpctl stdout: {repr(result.stdout)}")
        return result.stdout
    except Exception as e:
        logger.error(f"wpctl command failed: {e}")
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
    logger.debug("Getting default sink...")
    output = _run_wpctl(["status"])
    if not output:
        logger.warning("No output from wpctl status")
        return None
    
    logger.debug(f"wpctl status output lines: {len(output.splitlines())}")
    
    in_audio_section = False
    in_sinks_section = False
    
    for line_num, line in enumerate(output.splitlines(), 1):
        original_line = line
        line = line.strip()
        
        if line == "Audio":
            logger.debug(f"Found Audio section at line {line_num}")
            in_audio_section = True
            continue
        elif line == "Video" or line == "Settings":
            logger.debug(f"Exiting Audio section at line {line_num}: {line}")
            in_audio_section = False
            in_sinks_section = False
            continue
            
        if not in_audio_section:
            continue
            
        if "Sinks:" in line:
            logger.debug(f"Found Sinks section at line {line_num}")
            in_sinks_section = True
            continue
        elif "Sources:" in line or "Filters:" in line or "Streams:" in line:
            logger.debug(f"Exiting Sinks section at line {line_num}: {line}")
            in_sinks_section = False
            continue
            
        if in_sinks_section and line:
            logger.debug(f"Processing sink line {line_num}: {repr(original_line)}")
            # Look for lines with asterisk: " │  *   44. Built-in Audio Stereo               [vol: 0.71]"
            if '*' in original_line:
                logger.debug(f"Found default sink candidate at line {line_num}: {repr(original_line)}")
                clean_line = re.sub(r'^[│├└─\s]*\*?\s*', '', original_line)
                match = re.search(r'^(\d+)\.\s+(.+?)\s+\[', clean_line)
                if match:
                    node_id = match.group(1)
                    device_name = match.group(2).strip()
                    result = f"{node_id}:{device_name}"
                    logger.debug(f"Found default sink: {result}")
                    return result
                else:
                    logger.warning(f"Failed to parse default sink line: {repr(clean_line)}")
    
    logger.warning("No default sink found in wpctl status output")
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

def get_filtergraph_dot() -> Optional[str]:
    """Return the PipeWire filter/connection graph in GraphViz DOT format.

    Uses the 'pw-dot' tool (part of PipeWire) to dump the current graph.
    Returns the DOT text on success or None if the command fails or the
    utility is not available.
    """
    try:
        logger.debug("Running pw-dot to get filtergraph (DOT format)")
        # -o - writes to stdout
        result = subprocess.run(["pw-dot", "-o", "-"], capture_output=True, text=True, check=True)
        return result.stdout
    except FileNotFoundError:
        logger.error("pw-dot command not found. PipeWire tools may not be installed.")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"pw-dot failed with return code {e.returncode}: {e.stderr.strip() if e.stderr else e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error running pw-dot: {e}")
        return None

# ---------------------------------------------------------------------------
# Mixer balance / mono-stereo utilities (adapted from pw-balance script)
# ---------------------------------------------------------------------------

DEFAULT_SINK_NODE_NAME = "effect_input.proc"  # Documented virtual processing sink
MIXER_LEFT_NODE_NAME = "mixer_left"
MIXER_RIGHT_NODE_NAME = "mixer_right"

def _resolve_node_id_by_name(node_name: str) -> Optional[int]:
    """Resolve a PipeWire node id by its node.name property."""
    # pw-dump approach
    try:
        dump_out = subprocess.run(["pw-dump"], capture_output=True, text=True, check=True).stdout
        current = []
        for line in dump_out.splitlines():
            current.append(line)
            if line.strip() in ('},', '}'):
                block = "\n".join(current)
                if f'"node.name"' in block and f'"{node_name}"' in block:
                    m = re.search(r'"id"\s*:\s*(\d+)', block)
                    if m:
                        return int(m.group(1))
                current = []
    except Exception:
        pass
    # Fallback list/info
    try:
        ls_out = subprocess.run(["pw-cli", "ls", "Node"], capture_output=True, text=True, check=True).stdout
        for line in ls_out.splitlines():
            m = re.match(r'^(\d+):', line.strip())
            if not m:
                continue
            nid = m.group(1)
            try:
                info = subprocess.run(["pw-cli", "info", nid], capture_output=True, text=True, check=True).stdout
                if f'node.name = "{node_name}"' in info:
                    return int(nid)
            except Exception:
                continue
    except Exception:
        pass
    return None

def _resolve_mixer_node_ids() -> Tuple[Optional[int], Optional[int]]:
    """Resolve node ids for mixer_left and mixer_right nodes."""
    left = _resolve_node_id_by_name(MIXER_LEFT_NODE_NAME)
    right = _resolve_node_id_by_name(MIXER_RIGHT_NODE_NAME)
    return left, right

def _apply_mixer_gains(gL1: float, gL2: float, gR1: float, gR2: float) -> bool:
    """Apply mixer gains to mixer_left and mixer_right nodes.

    mixer_left  Gain 1 = Left->LeftOut   Gain 2 = Right->LeftOut
    mixer_right Gain 1 = Left->RightOut  Gain 2 = Right->RightOut
    """
    left_id, right_id = _resolve_mixer_node_ids()
    if left_id is None or right_id is None:
        logger.error("Could not resolve mixer node ids (left=%s right=%s)", left_id, right_id)
        return False
    try:
        p_left = '{ "Gain 1" = %0.6f "Gain 2" = %0.6f }' % (gL1, gL2)
        p_right = '{ "Gain 1" = %0.6f "Gain 2" = %0.6f }' % (gR1, gR2)
        rl = subprocess.run(["pw-cli", "set-param", str(left_id), "Props", p_left], capture_output=True, text=True)
        if rl.returncode != 0:
            logger.error("Failed setting left mixer gains: %s", rl.stderr.strip())
            return False
        rr = subprocess.run(["pw-cli", "set-param", str(right_id), "Props", p_right], capture_output=True, text=True)
        if rr.returncode != 0:
            logger.error("Failed setting right mixer gains: %s", rr.stderr.strip())
            return False
        # Update cache on success
        _last_mixer_gains.update({
            "mixer_left:Gain_1": gL1,
            "mixer_left:Gain_2": gL2,
            "mixer_right:Gain_1": gR1,
            "mixer_right:Gain_2": gR2,
        })
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying mixer gains: %s", e)
    return False

def _parse_gains_from_info(text: str, prefix: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    # Look for lines like:  \"Gain 1\" = 0.500000 or Gain 1 = 0.5
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'(?:"?)Gain\s+([0-9]+)(?:"?)\s*=\s*([0-9.]+)', line)
        if m:
            idx = m.group(1)
            val = m.group(2)
            try:
                out[f"{prefix}:Gain_{idx}"] = float(val)
            except ValueError:
                pass
    return out

def _get_mixer_status() -> Optional[Dict[str, float]]:
    left_id, right_id = _resolve_mixer_node_ids()
    if left_id is None or right_id is None:
        logger.warning("Mixer nodes not found (left=%s right=%s)", left_id, right_id)
        return None
    gains: Dict[str, float] = {}
    try:
        info_left = subprocess.run(["pw-cli", "info", str(left_id)], capture_output=True, text=True, check=True).stdout
        info_right = subprocess.run(["pw-cli", "info", str(right_id)], capture_output=True, text=True, check=True).stdout
        left_g = _parse_gains_from_info(info_left, "mixer_left")
        right_g = _parse_gains_from_info(info_right, "mixer_right")
        # We only care about Gain 1 & 2 for our balance/mono logic
        for k in list(left_g.keys()):
            if not k.endswith(('_1','_2')):
                left_g.pop(k)
        for k in list(right_g.keys()):
            if not k.endswith(('_1','_2')):
                right_g.pop(k)
        gains.update(left_g)
        gains.update(right_g)
    except Exception as e:
        logger.error("Failed retrieving mixer status: %s", e)
        return None
    if not gains:
        if _last_mixer_gains:
            logger.warning("No live mixer gains parsed; returning cached values.")
            return dict(_last_mixer_gains)
        logger.warning("No mixer gains parsed from pw-cli info output and no cache available.")
        return None
    return gains

def set_balance(balance: float, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set stereo balance. balance in [-1,1]; -1 full left, 0 center, +1 full right."""
    # Clamp
    try:
        b = float(balance)
    except ValueError:
        return False
    if b < -1:
        b = -1
    if b > 1:
        b = 1
    # Compute attenuations like script
    attL = 1 - b if b > 0 else 1.0
    attR = 1 + b if b < 0 else 1.0
    ok = _apply_mixer_gains(attL, 0.0, 0.0, attR)
    return ok

def set_mode(mode: str, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set channel mixing mode: mono, stereo, left, right."""
    mode = (mode or '').lower()
    if mode == 'mono':
        return _apply_mixer_gains(0.5, 0.5, 0.5, 0.5)
    if mode == 'stereo':
        return _apply_mixer_gains(1.0, 0.0, 0.0, 1.0)
    if mode == 'left':
        return _apply_mixer_gains(1.0, 0.0, 1.0, 0.0)
    if mode == 'right':
        return _apply_mixer_gains(0.0, 1.0, 0.0, 1.0)
    logger.error("Invalid mixer mode: %s", mode)
    return False

def get_mixer_status(node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> Optional[Dict[str, float]]:  # kept signature for API compatibility
    return _get_mixer_status()

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
        print("  config-pipewire mixer-status")
        print("  config-pipewire balance <B>")
        print("  config-pipewire mode <mono|stereo|left|right>")
        print("")
        print("  control_name: either 'node_id:device_name' or just 'node_id'")
        print("  volume: linear volume (0.0 - 1.0)")
        print("  volume_db: volume in decibels (e.g., -20.0)")
        print("  B: balance in [-1,1]; -1 full left, 0 center, +1 full right")

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
    elif cmd == "mixer-status":
        gains = get_mixer_status()
        if gains is None:
            print("Mixer status unavailable")
            sys.exit(5)
        for k,v in gains.items():
            print(f"{k}={v:.6f}")
    elif cmd == "balance" and len(sys.argv) == 3:
        try:
            b = float(sys.argv[2])
        except ValueError:
            print("Balance must be numeric in [-1,1]")
            sys.exit(3)
        if not set_balance(b):
            print("Failed to set balance")
            sys.exit(4)
        print("OK")
    elif cmd == "mode" and len(sys.argv) == 3:
        if not set_mode(sys.argv[2]):
            print("Invalid mode or failed to set (use mono|stereo|left|right)")
            sys.exit(4)
        print("OK")
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
