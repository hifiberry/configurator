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
_last_mixer_source: str = ""  # live | cache | default

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
    Returns the default hardware sink (using pw-dump to find ALSA output sink).
    Format: "node_id:device_name" or None if not found.
    """
    logger.debug("Getting default sink using pw-dump...")
    
    try:
        import json
        result = subprocess.run(["pw-dump"], capture_output=True, text=True, check=True)
        dump_data = json.loads(result.stdout)
        
        # Find audio sinks with alsa_output in node_name (hardware sinks)
        for item in dump_data:
            if (item.get("info", {}).get("props", {}).get("media.class") == "Audio/Sink" and
                item.get("info", {}).get("props", {}).get("node.name", "").startswith("alsa_output")):
                
                node_id = item.get("id")
                device_name = item.get("info", {}).get("props", {}).get("node.description", "Unknown")
                
                if node_id is not None:
                    result = f"{node_id}:{device_name}"
                    logger.debug(f"Found hardware sink via pw-dump: {result}")
                    return result
        
        logger.warning("No alsa_output sink found via pw-dump")
        return None
        
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"pw-dump failed: {e}")
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

DEFAULT_MIXER_NODE_NAME = "effect_input.proc"  # Container node with mixer params

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

def _resolve_mixer_container_node() -> Optional[int]:
    return _resolve_node_id_by_name(DEFAULT_MIXER_NODE_NAME)

def _apply_mixer_gains(gL1: float, gL2: float, gR1: float, gR2: float) -> bool:
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
    param = '{ "params": [ "mixer_left:Gain 1" %0.6f "mixer_left:Gain 2" %0.6f "mixer_right:Gain 1" %0.6f "mixer_right:Gain 2" %0.6f ] }' % (gL1, gL2, gR1, gR2)
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
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

def _get_mixer_status() -> Optional[Dict[str, float]]:
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.warning("Mixer container node not found")
        return None
    # Use global for source tracking; declare once before assignments
    global _last_mixer_source
    try:
        out = subprocess.run(["pw-cli", "enum-params", str(nid), "Props"], capture_output=True, text=True, check=True).stdout
        parsed: Dict[str, float] = {}
        lines = out.splitlines()
        # Strategy: support two formats
        # 1. key=value style (legacy regex below)
        # 2. Alternating lines: String "mixer_left:Gain 1" followed by Float value line
        # We'll first scan for String/Float pairs because that's the current observed format.
        i = 0
        while i < len(lines):
            raw = lines[i].strip()
            m_string = re.match(r'^String\s+"(mixer_(?:left|right):Gain\s+([0-9]+))"$', raw)
            if m_string:
                full_key = m_string.group(1)  # e.g. mixer_left:Gain 1
                # Look ahead for the Float value (can be same or subsequent lines; usually next line)
                j = i + 1
                while j < len(lines):
                    val_line = lines[j].strip()
                    m_float = re.match(r'^Float\s+([0-9]+(?:\.[0-9]+)?)$', val_line)
                    if m_float:
                        key_sanitized = full_key.replace(' ', '_')
                        try:
                            parsed[key_sanitized] = float(m_float.group(1))
                        except ValueError:
                            pass
                        i = j  # advance outer loop to float line
                        break
                    # Break early if another String encountered (value missing)
                    if val_line.startswith('String '):
                        break
                    j += 1
            else:
                # Legacy single-line format fallback
                m_legacy = re.match(r'"?(mixer_(?:left|right):Gain [0-9]+)"?\s*=\s*([0-9]+(?:\.[0-9]+)?)', raw)
                if m_legacy:
                    key = m_legacy.group(1).replace(' ', '_')
                    try:
                        parsed[key] = float(m_legacy.group(2))
                    except ValueError:
                        pass
            i += 1
        # Post-parse decision tree
        if parsed:
            _last_mixer_gains.update(parsed)
            _last_mixer_source = 'live'
            return dict(_last_mixer_gains)
        if _last_mixer_gains:
            logger.debug("Returning cached mixer gains (no numeric values exposed)")
            _last_mixer_source = 'cache'
            return dict(_last_mixer_gains)
        logger.warning("Mixer gains unavailable (no numeric values and no cache) - defaulting to stereo")
        _last_mixer_gains.update({
            "mixer_left:Gain_1": 1.0,
            "mixer_left:Gain_2": 0.0,
            "mixer_right:Gain_1": 0.0,
            "mixer_right:Gain_2": 1.0,
        })
        _last_mixer_source = 'default'
        return dict(_last_mixer_gains)
    except Exception as e:
        logger.debug("Failed to parse mixer gains (%s); using cache or default", e)
        if _last_mixer_gains:
            _last_mixer_source = 'cache'
            return dict(_last_mixer_gains)
        # default fallback
        _last_mixer_gains.update({
            "mixer_left:Gain_1": 1.0,
            "mixer_left:Gain_2": 0.0,
            "mixer_right:Gain_1": 0.0,
            "mixer_right:Gain_2": 1.0,
        })
        _last_mixer_source = 'default'
        return dict(_last_mixer_gains)

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

def set_mixer(mode: str = None, balance: float = None, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set channel mixing mode and/or balance in a single operation.
    
    Args:
        mode: Channel mixing mode ('mono', 'stereo', 'left', 'right'). 
        balance: Balance value in [-1,1] (-1 full left, 0 center, +1 full right).
                Can be used with any mode or by itself to adjust current mode.
        
    Returns:
        True if successful, False otherwise.
        
    Examples:
        set_mixer(mode='stereo')                    # Set to stereo, balance=0
        set_mixer(mode='mono')                      # Set to mono 
        set_mixer(mode='stereo', balance=-0.3)      # Set stereo with left bias
        set_mixer(balance=0.5)                      # Just adjust balance, keep current mode logic
    """
    if mode is None and balance is None:
        logger.error("Must specify either mode or balance")
        return False
        
    mode = (mode or '').lower()
    
    # Handle discrete modes with optional balance
    if mode == 'mono':
        return _apply_mixer_gains(0.5, 0.5, 0.5, 0.5)
    elif mode == 'stereo':
        if balance is not None:
            # Apply balance to stereo mode
            return set_balance(balance)
        else:
            return _apply_mixer_gains(1.0, 0.0, 0.0, 1.0)
    elif mode == 'left':
        return _apply_mixer_gains(1.0, 0.0, 1.0, 0.0)
    elif mode == 'right':
        return _apply_mixer_gains(0.0, 1.0, 0.0, 1.0)
    elif mode != '' and mode is not None:
        logger.error("Invalid mixer mode: %s", mode)
        return False
    
    # If we get here, mode was empty/None but balance was provided
    if balance is not None:
        return set_balance(balance)
    
    return False

def set_mode(mode: str, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set channel mixing mode: mono, stereo, left, right. (Legacy function - use set_mixer instead)"""
    return set_mixer(mode=mode, node_name=node_name, node_id=node_id)

def get_mixer_status(node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> Optional[Dict[str, float]]:  # kept signature for API compatibility
    return _get_mixer_status()

def analyze_mixer() -> Optional[Dict[str, Union[str, float]]]:
    """Infer logical mixer mode (mono|stereo|left|right|unknown) and balance value.

    Returns dict with keys:
      mode: inferred mode (mono, stereo, left, right, or unknown)
      balance: float in [-1,1] representing stereo balance
    or None if gains unavailable.
    """
    gains = _get_mixer_status()
    if gains is None:
        return None
    # Extract primary 4 gains (ignore additional mixer gains beyond 2 inputs)
    aL = gains.get("mixer_left:Gain_1")
    aR = gains.get("mixer_left:Gain_2")
    bL = gains.get("mixer_right:Gain_1")
    bR = gains.get("mixer_right:Gain_2")
    if None in (aL, aR, bL, bR):
        return None
    tol = 0.02
    def eq(x, y):
        return abs(x - y) <= tol
    mode = 'unknown'
    balance = 0.0
    # Recognize mono
    if eq(aL, aR) and eq(aR, bL) and eq(bL, bR) and eq(aL, 0.5):
        mode = 'mono'
        balance = 0.0
    # Left-only
    elif eq(aL, 1.0) and eq(bL, 1.0) and eq(aR, 0.0) and eq(bR, 0.0):
        mode = 'left'
        balance = -1.0
    # Right-only
    elif eq(aL, 0.0) and eq(bL, 0.0) and eq(aR, 1.0) and eq(bR, 1.0):
        mode = 'right'
        balance = 1.0
    # Stereo (default)
    elif eq(aL, 1.0) and eq(aR, 0.0) and eq(bL, 0.0) and eq(bR, 1.0):
        mode = 'stereo'
        balance = 0.0
    else:
        # Check for balanced stereo pattern produced by set_balance(): aR=bL=0, aL<=1, bR<=1 and at least one is 1
        if eq(aR, 0.0) and eq(bL, 0.0) and aL <= 1.0 + tol and bR <= 1.0 + tol:
            # This is a stereo configuration with balance adjustment
            mode = 'stereo'
            # Determine balance from attenuation
            if aL < 1.0 - tol and eq(bR, 1.0):  # right channel favored
                balance = 1.0 - aL  # positive balance
                balance = max(0.0, min(1.0, balance))
            elif bR < 1.0 - tol and eq(aL, 1.0):  # left channel favored  
                balance = bR - 1.0  # negative balance
                balance = max(-1.0, min(0.0, balance))
            elif eq(aL, 1.0) and eq(bR, 1.0):  # perfect center
                balance = 0.0
            else:
                # Both sides attenuated - use the side with less attenuation to determine balance direction
                if aL < bR:
                    balance = 1.0 - aL  # positive (right favored)
                else:
                    balance = bR - 1.0  # negative (left favored)
                # Clamp
                balance = max(-1.0, min(1.0, balance))
        else:
            mode = 'unknown'
            balance = 0.0
        else:
            mode = 'unknown'
            balance = 0.0
    return {"mode": mode, "balance": round(balance, 6)}

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
        print("  config-pipewire mixer-gains        # show individual gain values (live or cached)")
        print("  config-pipewire mixer-mode         # infer mode (mono/stereo/left/right/balance) + balance value")
        print("  config-pipewire mixer-save         # save current mixer mode/balance state")
        print("  config-pipewire mixer-restore      # restore saved mixer mode/balance state")
        print("  config-pipewire mixer <mode> [balance]  # set mode and optional balance in one command")
        print("  config-pipewire balance <B>")
        print("  config-pipewire mode <mono|stereo|left|right>")
        print("")
        print("  control_name: either 'node_id:device_name' or just 'node_id'")
        print("  volume: linear volume (0.0 - 1.0)")
        print("  volume_db: volume in decibels (e.g., -20.0)")
        print("  B: balance in [-1,1]; -1 full left, 0 center, +1 full right")
        print("  mixer examples:")
        print("    config-pipewire mixer stereo       # set stereo mode")
        print("    config-pipewire mixer balance -0.3 # set balance mode with left bias")
        print("    config-pipewire mixer mono         # set mono mode")

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
    elif cmd == "mixer-gains":
        gains = get_mixer_status()
        if gains is None:
            print("{}")
            sys.exit(5)
        # Print as simple JSON-ish line for easy parsing
        parts = [f"\"{k}\":{v:.6f}" for k,v in sorted(gains.items())]
        print('{'+', '.join(parts)+'}')
    elif cmd == "mixer-mode":
        info = analyze_mixer()
        if info is None:
            print("{}"); sys.exit(5)
        print(f"mode={info['mode']} balance={info['balance']}")
    elif cmd == "mixer-save":
        # Lazy import server settings manager via configdb to reuse storage mechanism if available
        try:
            from .configdb import ConfigDB
            db = ConfigDB()
            from .settings_manager import SettingsManager
            sm = SettingsManager(db)
            # Register ephemeral callbacks matching server logic
            def save_cb():
                analysis = analyze_mixer()
                if not analysis or analysis.get('mode') in (None,'unknown'):
                    return None
                return f"{analysis['mode']},{analysis['balance']:.6f}"
            def restore_cb(val):
                pass  # not needed here
            sm.register_setting('pipewire_mixer_state', save_cb, restore_cb)
            if sm.save_setting('pipewire_mixer_state'):
                print("OK")
            else:
                print("Failed")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(6)
    elif cmd == "mixer-restore":
        try:
            from .configdb import ConfigDB
            db = ConfigDB()
            from .settings_manager import SettingsManager
            sm = SettingsManager(db)
            # Provide dummy save; real restore applies using set_mode/set_balance
            def save_cb():
                return None
            def restore_cb(val):
                parts = str(val).split(',')
                if len(parts)!=2:
                    return False
                mode = parts[0]
                try:
                    bal = float(parts[1])
                except Exception:
                    bal = 0.0
                if mode in {'mono','stereo','left','right'}:
                    return set_mode(mode)
                if mode=='balance':
                    return set_balance(bal)
                return False
            sm.register_setting('pipewire_mixer_state', save_cb, restore_cb)
            if sm.restore_setting('pipewire_mixer_state'):
                print("OK")
            else:
                print("Failed")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(6)
    elif cmd == "mixer" and len(sys.argv) >= 3:
        # Combined mixer command: mixer <mode> [balance]
        mode_arg = sys.argv[2]
        balance_arg = None
        
        if len(sys.argv) == 4:
            try:
                balance_arg = float(sys.argv[3])
            except ValueError:
                print("Balance must be numeric in [-1,1]")
                sys.exit(3)
        
        # If mode is 'balance' and no balance arg provided, error
        if mode_arg == 'balance' and balance_arg is None:
            print("Balance value required for balance mode")
            sys.exit(3)
        
        if not set_mixer(mode=mode_arg, balance=balance_arg):
            print("Failed to set mixer")
            sys.exit(4)
        print("OK")
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
