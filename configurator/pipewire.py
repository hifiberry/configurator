"""
pipewire.py - PipeWire volume & mixer control utility

Provides functions to list controls, get/set volume (linear & dB), dump the
connection graph (pw-dot) and manipulate a custom filter-chain based mixer for
balance / monostereo / channel routing.

Node name assumptions for monostereo/balance features:
    - Virtual processing sink (what regular applications target): effect_input.proc
    - (Optional) Passive output node name: effect_output.proc
    - Parametric EQ node (16 peaking filters per channel): peq
    - Two monostereo mixer nodes for mono/stereo/left/right/swapped modes:
                monostereo_left
                monostereo_right
    - Two balance mixer nodes for left-right crossfeed:
                balance_left
                balance_right

Expected gain parameter names exposed by PipeWire:

Monostereo mixers (pw-cli enum-params <mixer_id> Props):
    monostereo_left:Gain 1   (Left  input -> Left output)
    monostereo_left:Gain 2   (Right input -> Left output)
    monostereo_right:Gain 1  (Left  input -> Right output)
    monostereo_right:Gain 2  (Right input -> Right output)

Balance mixers (pw-cli enum-params <mixer_id> Props):
    balance_left:Gain 1   (Left  input -> Left output)
    balance_left:Gain 2   (Right input -> Left output)
    balance_right:Gain 1  (Left  input -> Right output)
    balance_right:Gain 2  (Right input -> Right output)

Reference filter-chain configuration (for documentation only):
-----------------------------------------------------------------
### Monostereo + Balance + Parametric EQ (16-band peaking) sink
# Single virtual sink so ALSA clients attach here: effect_input.proc
# Processing order: Input (stereo) -> monostereo (stereo/mono/left-only/right-only)
#                 -> balance (left-right image/crossfeed)
#                 -> param_eq (multi-channel, 16 peaking filters per channel, no shelves)
# Output goes directly to hardware via standard routing.
#
# Monostereo presets (set gains on monostereo_* nodes):
#  - stereo:      L {1.0, 0.0}  R {0.0, 1.0}
#  - mono:        L {0.5, 0.5}  R {0.5, 0.5}
#  - left-only:   L {1.0, 0.0}  R {1.0, 0.0}
#  - right-only:  L {0.0, 1.0}  R {0.0, 1.0}
#
# Balance math (external): Given balance B in [-1,1]
#  Compute crossfeed gains and set on balance_* nodes:
#   balance_left  : Gain 1 = (1 - B/2)     Gain 2 = (-B/2)
#   balance_right : Gain 1 = (-B/2)        Gain 2 = (1 + B/2)
# Normalize if any |gain|>1.0 by dividing all by max|gain|. Center (B=0): left (1,0) right (0,1)
#
# Adjust gains at runtime (example Mono):
#  L=$(pw-cli ls Node | awk '/monostereo_left/{print $1;exit}'|tr -d :) ; R=$(pw-cli ls Node | awk '/monostereo_right/{print $1;exit}'|tr -d :) ; \
#  pw-cli set-param $L Props '{ "Gain 1" = 0.5 "Gain 2" = 0.5 }' ; pw-cli set-param $R Props '{ "Gain 1" = 0.5 "Gain 2" = 0.5 }'
#
# Adjust balance (example center):
#  BL=$(pw-cli ls Node | awk '/balance_left/{print $1;exit}'|tr -d :) ; BR=$(pw-cli ls Node | awk '/balance_right/{print $1;exit}'|tr -d :) ; \
#  pw-cli set-param $BL Props '{ "Gain 1" = 1.0 "Gain 2" = 0.0 }' ; pw-cli set-param $BR Props '{ "Gain 1" = 0.0 "Gain 2" = 1.0 }'
#
context.modules = [
  { name = libpipewire-module-filter-chain
    args = {
      node.description = "EQ + Balance Sink"
      media.name       = "EQ + Balance Sink"
      filter.graph = {
        nodes = [
          # Input copy nodes (provide fan-out of external L/R to both monostereo mixers)
          { type = builtin label = copy name = in_left }
          { type = builtin label = copy name = in_right }
          
          # Monostereo stage: mixes L/R into stereo/mono/left-only/right-only
          { type = builtin label = mixer name = monostereo_left  control = { "Gain 1" = 1.0 "Gain 2" = 0.0 } }
          { type = builtin label = mixer name = monostereo_right control = { "Gain 1" = 0.0 "Gain 2" = 1.0 } }

          # Balance stage: crossfeed between post-monostereo L/R
          { type = builtin label = mixer name = balance_left  control = { "Gain 1" = 1.0 "Gain 2" = 0.0 } }
          { type = builtin label = mixer name = balance_right control = { "Gain 1" = 0.0 "Gain 2" = 1.0 } }

          # Parametric EQ (applies same 16 peaking filters to each channel independently) — final stage
          { type = builtin label = param_eq name = peq
            config = {
              filters = [
                { type = bq_peaking freq = 32.0    gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 50.0    gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 80.0    gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 125.0   gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 200.0   gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 315.0   gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 500.0   gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 800.0   gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 1250.0  gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 2000.0  gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 3150.0  gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 5000.0  gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 8000.0  gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 10000.0 gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 16000.0 gain = 0.0 q = 1.0 }
                { type = bq_peaking freq = 20000.0 gain = 0.0 q = 1.0 }
              ]
            }
          }
        ]
        links = [
          # Feed inputs to copy nodes
          # (External inputs are attached to in_left:In and in_right:In via the graph's inputs[] specification below)

          # Fan-out copy outputs into monostereo mixers (each takes both inputs)
          { output = "in_left:Out"  input = "monostereo_left:In 1" }
          { output = "in_right:Out" input = "monostereo_left:In 2" }
          { output = "in_left:Out"  input = "monostereo_right:In 1" }
          { output = "in_right:Out" input = "monostereo_right:In 2" }

          # Feed monostereo outputs into balance mixers (cross-mix for balance)
          { output = "monostereo_left:Out"  input = "balance_left:In 1" }
          { output = "monostereo_right:Out" input = "balance_left:In 2" }
          { output = "monostereo_left:Out"  input = "balance_right:In 1" }
          { output = "monostereo_right:Out" input = "balance_right:In 2" }

          # Final EQ stage per channel
          { output = "balance_left:Out"  input = "peq:In 1" }
          { output = "balance_right:Out" input = "peq:In 2" }
        ]
        inputs  = [ "in_left:In" "in_right:In" ]
        outputs = [ "peq:Out 1" "peq:Out 2" ]
      }
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props = {
        node.name = "effect_input.proc"
        media.class = Audio/Sink
        node.virtual = true            # Hint it's a processing virtual sink
        priority.session = 2000        # Higher than physical sinks (often 1000)
        priority.driver = 2000
      }
      playback.props = { node.name = "effect_output.proc" node.passive = true }
    }
  }
]

# Make this the default sink
context.properties = { default.audio.sink = effect_input.proc }
-----------------------------------------------------------------

This configuration is not auto-deployed by this module; it documents the
assumed topology for monostereo and balance manipulation. If your node names 
differ, you can override them by extending the helper functions to accept custom names.
"""
import subprocess
import re
import math
import logging
import time
import os
from typing import List, Optional, Tuple, Dict, Union

logger = logging.getLogger(__name__)

# Cache for last applied mixer gains (used when PipeWire can't report them)
_last_mixer_gains: Dict[str, float] = {}
_last_mixer_source: str = ""  # live | cache | default

def _run_wpctl(args: List[str]) -> Optional[str]:
    try:
        logger.debug(f"Running wpctl command: wpctl {' '.join(args)}")
        result = subprocess.run(["wpctl"] + args, capture_output=True, text=True, check=False)
        
        logger.debug(f"wpctl return code: {result.returncode}")
        logger.debug(f"wpctl stdout length: {len(result.stdout)}")
        logger.debug(f"wpctl stderr length: {len(result.stderr)}")
        
        if len(result.stdout) < 500:  # Only log short outputs to avoid spam
            logger.debug(f"wpctl stdout: {repr(result.stdout)}")
        if result.stderr:
            logger.debug(f"wpctl stderr: {repr(result.stderr)}")
            
        if result.returncode != 0:
            # Check if it's a PipeWire connection error
            stderr_lower = result.stderr.lower()
            if 'could not connect' in stderr_lower or 'connection' in stderr_lower:
                raise RuntimeError("Could not connect to PipeWire. Is the PipeWire service running?")
            logger.error(f"wpctl command failed with return code {result.returncode}: {result.stderr}")
            return None
            
        return result.stdout
    except RuntimeError:
        # Re-raise RuntimeError (PipeWire connection issues)
        raise
    except Exception as e:
        logger.error(f"wpctl command failed: {e}")
        return None

def get_wpctl_debug_info() -> dict:
    """
    Get detailed debugging information about wpctl command execution.
    
    Returns:
        Dictionary with debugging information including stdout, stderr, return codes
    """
    debug_info = {
        'timestamp': time.time(),
        'environment': {},
        'commands': {}
    }
    
    # Capture relevant environment variables
    env_vars = ['XDG_RUNTIME_DIR', 'PIPEWIRE_RUNTIME_DIR', 'PULSE_RUNTIME_PATH', 'USER', 'HOME']
    for var in env_vars:
        debug_info['environment'][var] = os.environ.get(var, 'NOT_SET')
    
    # Test various wpctl commands
    test_commands = [
        ['--version'],
        ['status'],
        ['get-volume', '@DEFAULT_AUDIO_SINK@']
    ]
    
    for cmd_args in test_commands:
        cmd_key = ' '.join(cmd_args)
        try:
            logger.debug(f"Debug: Running wpctl command: wpctl {cmd_key}")
            result = subprocess.run(["wpctl"] + cmd_args, capture_output=True, text=True, check=False, timeout=5)
            
            debug_info['commands'][cmd_key] = {
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            debug_info['commands'][cmd_key] = {
                'return_code': -1,
                'stdout': '',
                'stderr': 'Command timed out',
                'success': False
            }
        except Exception as e:
            debug_info['commands'][cmd_key] = {
                'return_code': -2,
                'stdout': '',
                'stderr': str(e),
                'success': False
            }
    
    return debug_info

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

def get_devices() -> Optional[Dict[str, List[str]]]:
    """
    Returns all PipeWire devices categorized by type.
    Returns a dictionary with keys: 'sinks', 'sources'
    Each value is a list of "node_id:device_name" strings.
    Returns None if PipeWire is not available.
    """
    try:
        output = _run_wpctl(["status"])
    except RuntimeError:
        # PipeWire not available
        return None
    if output is None:
        return None
    if not output:
        return {'sinks': [], 'sources': []}
    
    devices = {'sinks': [], 'sources': []}
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
                device_str = f"{node_id}:{device_name}"
                if in_sinks_section:
                    devices['sinks'].append(device_str)
                elif in_sources_section:
                    devices['sources'].append(device_str)
    
    return devices

def get_volume_controls() -> Optional[List[str]]:
    """
    Deprecated: Use get_devices() instead.
    Returns a list of all PipeWire volume control names using wpctl.
    Format: "node_id:device_name"
    Returns None if PipeWire is not available.
    """
    devices = get_devices()
    if devices is None:
        return None
    # Combine sinks and sources for backward compatibility
    return devices['sinks'] + devices['sources']

def get_all_controls() -> Optional[Dict[str, List[str]]]:
    """
    Returns all PipeWire controls categorized by type.
    Returns a dictionary with keys: 'sinks', 'sources', 'filters', 'sink_streams', 'source_streams'
    Each value is a list of "node_id:device_name" strings.
    Returns None if PipeWire is not available.
    """
    try:
        output = _run_wpctl(["status"])
    except RuntimeError:
        # PipeWire not available
        return None
    if output is None:
        return None
    if not output:
        return {'sinks': [], 'sources': [], 'filters': [], 'sink_streams': [], 'source_streams': []}
    
    result = {
        'sinks': [],
        'sources': [],
        'filters': [],
        'sink_streams': [],
        'source_streams': []
    }
    
    in_audio_section = False
    current_section = None
    
    for line in output.splitlines():
        original_line = line
        line = line.strip()
        
        if line == "Audio":
            in_audio_section = True
            continue
        elif line == "Video" or line == "Settings":
            in_audio_section = False
            current_section = None
            continue
            
        if not in_audio_section:
            continue
            
        # Detect section headers
        if "Sinks:" in line:
            current_section = 'sinks'
            continue
        elif "Sources:" in line:
            current_section = 'sources'
            continue
        elif "Filters:" in line:
            current_section = 'filters'
            continue
        elif "Sink endpoints:" in line or "Source endpoints:" in line:
            current_section = None  # Skip endpoints
            continue
        elif "Streams:" in line:
            # Need to detect if it's under Sinks or Sources
            continue
        elif "Sink streams:" in line:
            current_section = 'sink_streams'
            continue
        elif "Source streams:" in line:
            current_section = 'source_streams'
            continue
            
        if current_section and line:
            # Parse lines like: " │  *   44. Built-in Audio Stereo               [vol: 0.60]"
            # Remove tree characters and asterisks
            clean_line = re.sub(r'^[│├└─\s]*\*?\s*', '', original_line)
            match = re.search(r'^(\d+)\.\s+(.+?)(?:\s+\[|$)', clean_line)
            if match:
                node_id = match.group(1)
                device_name = match.group(2).strip()
                result[current_section].append(f"{node_id}:{device_name}")
    
    return result

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

def _apply_monostereo_gains(gL1: float, gL2: float, gR1: float, gR2: float) -> bool:
    """Apply gains to monostereo mixer nodes."""
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
    param = '{ "params": [ "monostereo_left:Gain 1" %0.6f "monostereo_left:Gain 2" %0.6f "monostereo_right:Gain 1" %0.6f "monostereo_right:Gain 2" %0.6f ] }' % (gL1, gL2, gR1, gR2)
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
        _last_mixer_gains.update({
            "monostereo_left:Gain_1": gL1,
            "monostereo_left:Gain_2": gL2,
            "monostereo_right:Gain_1": gR1,
            "monostereo_right:Gain_2": gR2,
        })
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying monostereo gains: %s", e)
    return False

def _apply_balance_gains(gL1: float, gL2: float, gR1: float, gR2: float) -> bool:
    """Apply gains to balance mixer nodes."""
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
    param = '{ "params": [ "balance_left:Gain 1" %0.6f "balance_left:Gain 2" %0.6f "balance_right:Gain 1" %0.6f "balance_right:Gain 2" %0.6f ] }' % (gL1, gL2, gR1, gR2)
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
        _last_mixer_gains.update({
            "balance_left:Gain_1": gL1,
            "balance_left:Gain_2": gL2,
            "balance_right:Gain_1": gR1,
            "balance_right:Gain_2": gR2,
        })
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying balance gains: %s", e)
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
        # 2. Alternating lines: String "mixer_name:Gain 1" followed by Float value line
        # We'll first scan for String/Float pairs because that's the current observed format.
        i = 0
        while i < len(lines):
            raw = lines[i].strip()
            # Look for both monostereo and balance mixer nodes
            m_string = re.match(r'^String\s+"((monostereo_|balance_)(?:left|right):Gain\s+([0-9]+))"$', raw)
            if m_string:
                full_key = m_string.group(1)  # e.g. monostereo_left:Gain 1
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
                m_legacy = re.match(r'"?((monostereo_|balance_)(?:left|right):Gain [0-9]+)"?\s*=\s*([0-9]+(?:\.[0-9]+)?)', raw)
                if m_legacy:
                    key = m_legacy.group(1).replace(' ', '_')
                    try:
                        parsed[key] = float(m_legacy.group(3))
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
            "monostereo_left:Gain_1": 1.0,
            "monostereo_left:Gain_2": 0.0,
            "monostereo_right:Gain_1": 0.0,
            "monostereo_right:Gain_2": 1.0,
            "balance_left:Gain_1": 1.0,
            "balance_left:Gain_2": 0.0,
            "balance_right:Gain_1": 0.0,
            "balance_right:Gain_2": 1.0,
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
            "monostereo_left:Gain_1": 1.0,
            "monostereo_left:Gain_2": 0.0,
            "monostereo_right:Gain_1": 0.0,
            "monostereo_right:Gain_2": 1.0,
            "balance_left:Gain_1": 1.0,
            "balance_left:Gain_2": 0.0,
            "balance_right:Gain_1": 0.0,
            "balance_right:Gain_2": 1.0,
        })
        _last_mixer_source = 'default'
        return dict(_last_mixer_gains)

def set_monostereo(mode: str, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set monostereo mode: stereo, mono, left, right, swapped.
    
    Args:
        mode: Channel mixing mode ('mono', 'stereo', 'left', 'right', 'swapped')
        
    Returns:
        True if successful, False otherwise.
    """
    mode = (mode or '').lower()
    
    if mode == 'stereo':
        return _apply_monostereo_gains(1.0, 0.0, 0.0, 1.0)
    elif mode == 'mono':
        return _apply_monostereo_gains(0.5, 0.5, 0.5, 0.5)
    elif mode == 'left':
        return _apply_monostereo_gains(1.0, 0.0, 1.0, 0.0)
    elif mode == 'right':
        return _apply_monostereo_gains(0.0, 1.0, 0.0, 1.0)
    elif mode == 'swapped':
        return _apply_monostereo_gains(0.0, 1.0, 1.0, 0.0)
    else:
        logger.error("Invalid monostereo mode: %s (use stereo|mono|left|right|swapped)", mode)
        return False

def set_balance(balance: float, *, node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> bool:
    """Set stereo balance using crossfeed. balance in [-1,1]; -1 full left, 0 center, +1 full right.
    
    Uses the new balance math:
    balance_left  : Gain 1 = (1 - B/2)     Gain 2 = (-B/2)
    balance_right : Gain 1 = (-B/2)        Gain 2 = (1 + B/2)
    Normalize if any |gain|>1.0 by dividing all by max|gain|.
    """
    # Clamp balance
    try:
        b = float(balance)
    except ValueError:
        return False
    if b < -1:
        b = -1
    if b > 1:
        b = 1
    
    # Compute crossfeed gains using the new balance math
    gL1 = 1 - b/2    # balance_left:Gain 1
    gL2 = -b/2       # balance_left:Gain 2
    gR1 = -b/2       # balance_right:Gain 1
    gR2 = 1 + b/2    # balance_right:Gain 2
    
    # Normalize if any |gain| > 1.0
    max_gain = max(abs(gL1), abs(gL2), abs(gR1), abs(gR2))
    if max_gain > 1.0:
        gL1 /= max_gain
        gL2 /= max_gain
        gR1 /= max_gain
        gR2 /= max_gain
    
    return _apply_balance_gains(gL1, gL2, gR1, gR2)

def get_mixer_status(node_name: Optional[str] = None, node_id: Optional[Union[str,int]] = None) -> Optional[Dict[str, float]]:  # kept signature for API compatibility
    return _get_mixer_status()

def get_monostereo() -> Optional[str]:
    """Get current monostereo mode by analyzing mixer gains.
    
    Returns:
        String indicating current mode: 'stereo', 'mono', 'left', 'right', or 'unknown'
        None if gains unavailable.
    """
    gains = _get_mixer_status()
    if gains is None:
        return None
    
    # Extract monostereo gains
    mL1 = gains.get("monostereo_left:Gain_1")
    mL2 = gains.get("monostereo_left:Gain_2")
    mR1 = gains.get("monostereo_right:Gain_1")
    mR2 = gains.get("monostereo_right:Gain_2")
    
    if None in (mL1, mL2, mR1, mR2):
        return None
    
    tol = 0.02
    def eq(x, y):
        return abs(x - y) <= tol
    
    # Recognize stereo
    if eq(mL1, 1.0) and eq(mL2, 0.0) and eq(mR1, 0.0) and eq(mR2, 1.0):
        return 'stereo'
    # Recognize mono
    elif eq(mL1, 0.5) and eq(mL2, 0.5) and eq(mR1, 0.5) and eq(mR2, 0.5):
        return 'mono'
    # Left-only
    elif eq(mL1, 1.0) and eq(mL2, 0.0) and eq(mR1, 1.0) and eq(mR2, 0.0):
        return 'left'
    # Right-only
    elif eq(mL1, 0.0) and eq(mL2, 1.0) and eq(mR1, 0.0) and eq(mR2, 1.0):
        return 'right'
    # Swapped (left input to right output, right input to left output)
    elif eq(mL1, 0.0) and eq(mL2, 1.0) and eq(mR1, 1.0) and eq(mR2, 0.0):
        return 'swapped'
    else:
        return 'unknown'

def get_balance() -> Optional[float]:
    """Get current balance value by analyzing balance mixer gains.
    
    Returns:
        Float in [-1,1] representing stereo balance (-1 full left, 0 center, +1 full right)
        None if gains unavailable.
    """
    gains = _get_mixer_status()
    if gains is None:
        return None
    
    # Extract balance gains
    bL1 = gains.get("balance_left:Gain_1")
    bL2 = gains.get("balance_left:Gain_2")
    bR1 = gains.get("balance_right:Gain_1")
    bR2 = gains.get("balance_right:Gain_2")
    
    if None in (bL1, bL2, bR1, bR2):
        return None
    
    tol = 0.02
    def eq(x, y):
        return abs(x - y) <= tol
    
    # Check for perfect center/bypass case first
    if eq(bL1, 1.0) and eq(bL2, 0.0) and eq(bR1, 0.0) and eq(bR2, 1.0):
        return 0.0
    
    # Try to reverse the balance math, accounting for normalization:
    # Original balance math (before normalization):
    # balance_left  : Gain 1 = (1 - B/2)     Gain 2 = (-B/2)
    # balance_right : Gain 1 = (-B/2)        Gain 2 = (1 + B/2)
    
    # Check if it follows the crossfeed pattern (crossfeed gains should be equal)
    if eq(bL2, bR1):  # Crossfeed gains should be equal
        crossfeed = bL2  # = bR1 = normalized(-B/2)
        
        # To find B, we need to account for possible normalization
        # If normalized, the ratio between gains is preserved:
        # crossfeed / main_gain = (-B/2) / (1 ± B/2)
        
        # Use the larger of the two main gains to calculate balance
        # bL1 corresponds to (1 - B/2), bR2 corresponds to (1 + B/2)
        if abs(bR2) >= abs(bL1):
            # Use right channel as reference: bR2 = normalized(1 + B/2)
            # crossfeed = normalized(-B/2)
            # So: crossfeed / bR2 = (-B/2) / (1 + B/2) = -B / (2 + B)
            # Solve for B: crossfeed * (2 + B) = -B * bR2
            # crossfeed * 2 + crossfeed * B = -B * bR2  
            # crossfeed * 2 = -B * bR2 - crossfeed * B
            # crossfeed * 2 = -B * (bR2 + crossfeed)
            # B = -2 * crossfeed / (bR2 + crossfeed)
            if abs(bR2 + crossfeed) > 1e-6:  # Avoid division by zero
                balance = -2 * crossfeed / (bR2 + crossfeed)
            else:
                balance = 0.0
        else:
            # Use left channel as reference: bL1 = normalized(1 - B/2)
            # crossfeed = normalized(-B/2)  
            # So: crossfeed / bL1 = (-B/2) / (1 - B/2) = -B / (2 - B)
            # Solve for B: crossfeed * (2 - B) = -B * bL1
            # crossfeed * 2 - crossfeed * B = -B * bL1
            # crossfeed * 2 = -B * bL1 + crossfeed * B
            # crossfeed * 2 = B * (crossfeed - bL1)
            # B = 2 * crossfeed / (crossfeed - bL1)
            if abs(crossfeed - bL1) > 1e-6:  # Avoid division by zero
                balance = 2 * crossfeed / (crossfeed - bL1)
            else:
                balance = 0.0
        
        # Clamp to valid range and return
        balance = max(-1.0, min(1.0, balance))
        return round(balance, 6)
    
    # Default to center if pattern doesn't match
    return 0.0

def analyze_mixer() -> Optional[Dict[str, any]]:
    """
    Analyze current mixer gains to infer monostereo mode and balance.
    
    Returns:
        dict: Dictionary with 'monostereo_mode' and 'balance' keys, or None if unavailable
    """
    try:
        # Get current monostereo mode and balance
        monostereo_mode = get_monostereo()
        balance = get_balance()
        
        if monostereo_mode is None or balance is None:
            logger.warning("Cannot analyze mixer: unable to get current monostereo mode or balance")
            return None
            
        return {
            'monostereo_mode': monostereo_mode,
            'balance': balance
        }
        
    except Exception as e:
        logger.error(f"Error analyzing mixer: {e}")
        return None

def main():
    import sys
    def print_usage():
        print("Usage:")
        print("  config-pipewire list")
        print("  config-pipewire list-all")
        print("  config-pipewire default-sink")
        print("  config-pipewire default-source")
        print("  config-pipewire get <control_name>")
        print("  config-pipewire get-db <control_name>")
        print("  config-pipewire set <control_name> <volume>")
        print("  config-pipewire set-db <control_name> <volume_db>")
        print("  config-pipewire get-monostereo     # get current monostereo mode")
        print("  config-pipewire get-balance        # get current balance value")
        print("  config-pipewire mixer-save         # save current mixer state")
        print("  config-pipewire mixer-restore      # restore saved mixer state")
        print("  config-pipewire monostereo <mode>  # set monostereo mode")
        print("  config-pipewire balance <B>        # set balance")
        print("")
        print("  control_name: either 'node_id:device_name' or just 'node_id'")
        print("  volume: linear volume (0.0 - 1.0)")
        print("  volume_db: volume in decibels (e.g., -20.0)")
        print("  mode: stereo, mono, left, right, swapped")
        print("  B: balance in [-1,1]; -1 full left, 0 center, +1 full right")
        print("  examples:")
        print("    config-pipewire monostereo stereo  # set stereo mode")
        print("    config-pipewire balance -0.3       # set left bias")
        print("    config-pipewire get-monostereo     # get current mode")
        print("    config-pipewire get-balance        # get current balance")

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        devices = get_devices()
        if devices is None:
            print("Error: Could not connect to PipeWire. Is the PipeWire service running?", file=sys.stderr)
            sys.exit(2)
        if devices['sinks']:
            print("\nSINKS:")
            for d in devices['sinks']:
                print(f"  {d}")
        if devices['sources']:
            print("\nSOURCES:")
            for d in devices['sources']:
                print(f"  {d}")
    elif cmd == "list-all":
        all_controls = get_all_controls()
        if all_controls is None:
            print("Error: Could not connect to PipeWire. Is the PipeWire service running?", file=sys.stderr)
            sys.exit(2)
        for category, controls in all_controls.items():
            if controls:
                print(f"\n{category.upper().replace('_', ' ')}:")
                for c in controls:
                    print(f"  {c}")
    elif cmd == "default-sink":
        try:
            default_sink = get_default_sink()
            if default_sink:
                print(default_sink)
            else:
                print("No default sink found")
                sys.exit(2)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)
    elif cmd == "default-source":
        try:
            default_source = get_default_source()
            if default_source:
                print(default_source)
            else:
                print("No default source found")
                sys.exit(2)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
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
    elif cmd == "get-monostereo":
        mode = get_monostereo()
        if mode is None:
            print("Monostereo status unavailable")
            sys.exit(5)
        print(mode)
    elif cmd == "get-balance":
        balance = get_balance()
        if balance is None:
            print("Balance status unavailable")
            sys.exit(5)
        print(f"{balance:.6f}")
    elif cmd == "mixer-save":
        # Lazy import server settings manager via configdb to reuse storage mechanism if available
        try:
            from .configdb import ConfigDB
            db = ConfigDB()
            from .settings_manager import SettingsManager
            sm = SettingsManager(db)
            # Register ephemeral callbacks matching server logic
            def save_cb():
                mode = get_monostereo()
                balance = get_balance()
                if mode is None or mode == 'unknown':
                    return None
                if balance is None:
                    balance = 0.0
                return f"{mode},{balance:.6f}"
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
            # Provide dummy save; real restore applies using set_monostereo/set_balance
            def save_cb():
                return None
            def restore_cb(val):
                parts = str(val).split(',')
                if len(parts) != 2:
                    return False
                mode = parts[0]
                try:
                    bal = float(parts[1])
                except Exception:
                    bal = 0.0
                success = True
                if mode in {'mono','stereo','left','right'}:
                    success &= set_monostereo(mode)
                if abs(bal) > 0.001:  # Only set balance if it's not essentially zero
                    success &= set_balance(bal)
                return success
            sm.register_setting('pipewire_mixer_state', save_cb, restore_cb)
            if sm.restore_setting('pipewire_mixer_state'):
                print("OK")
            else:
                print("Failed")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(6)
    elif cmd == "monostereo" and len(sys.argv) == 3:
        mode = sys.argv[2]
        if not set_monostereo(mode):
            print("Invalid mode or failed to set (use stereo|mono|left|right)")
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
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
