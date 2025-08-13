"""
pipewire.py - PipeWire volume & mixer control utility

Provides functions to list controls, get/set volume (linear & dB), dump the
connection graph (pw-dot) and manipulate a custom filter-chain based mixer for
balance / monostereo / channel routing.

Node name assumptions for monostereo/balance features:
    - Virtual processing sink (what regular applications target): effect_input.proc
    - (Optional) Passive output node name: effect_output.proc
    - Parametric EQ node (16 peaking filters per channel): peq
    - Two monostereo mixer nodes for mono/stereo/left/right modes:
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
### Monostereo + Balance + Parametric EQ (16-band peaking, dynamic) sink
# Single virtual sink so ALSA clients attach here: effect_input.proc
# Processing order: Input (stereo) -> monostereo (stereo/mono/left-only/right-only)
#                 -> balance (left-right image/crossfeed)
#                 -> 16x bq_peaking (multi-channel, same filters per channel, no shelves)
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
# EQ Controls (runtime adjustable):
# Left channel EQ nodes: eqL01 to eqL16, each with Freq, Q, Gain controls
# Right channel EQ nodes: eqR01 to eqR16, each with Freq, Q, Gain controls
# Example: Set EQ1 left channel to 80Hz, Q=1.5, Gain=-3dB:
#  pw-cli set-param <container_node_id> Props '{ "eqL01:Freq" = 80.0 "eqL01:Q" = 1.5 "eqL01:Gain" = -3.0 }'
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
          
          # Parametric EQ Left Channel (16x peaking biquads in series)
          { type = builtin label = bq_peaking name = eqL01 control = { Freq = 32.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL02 control = { Freq = 50.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL03 control = { Freq = 80.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL04 control = { Freq = 125.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL05 control = { Freq = 200.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL06 control = { Freq = 315.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL07 control = { Freq = 500.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL08 control = { Freq = 800.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL09 control = { Freq = 1250.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL10 control = { Freq = 2000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL11 control = { Freq = 3150.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL12 control = { Freq = 5000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL13 control = { Freq = 8000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL14 control = { Freq = 10000.0 Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL15 control = { Freq = 16000.0 Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqL16 control = { Freq = 20000.0 Q = 1.0 Gain = 0.0 } }

          # Parametric EQ Right Channel (16x peaking biquads in series)
          { type = builtin label = bq_peaking name = eqR01 control = { Freq = 32.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR02 control = { Freq = 50.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR03 control = { Freq = 80.0    Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR04 control = { Freq = 125.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR05 control = { Freq = 200.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR06 control = { Freq = 315.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR07 control = { Freq = 500.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR08 control = { Freq = 800.0   Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR09 control = { Freq = 1250.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR10 control = { Freq = 2000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR11 control = { Freq = 3150.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR12 control = { Freq = 5000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR13 control = { Freq = 8000.0  Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR14 control = { Freq = 10000.0 Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR15 control = { Freq = 16000.0 Q = 1.0 Gain = 0.0 } }
          { type = builtin label = bq_peaking name = eqR16 control = { Freq = 20000.0 Q = 1.0 Gain = 0.0 } }
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

          # Left EQ chain (16 peaking filters in series)
          { output = "balance_left:Out"  input = "eqL01:In" }
          { output = "eqL01:Out" input = "eqL02:In" }
          { output = "eqL02:Out" input = "eqL03:In" }
          { output = "eqL03:Out" input = "eqL04:In" }
          { output = "eqL04:Out" input = "eqL05:In" }
          { output = "eqL05:Out" input = "eqL06:In" }
          { output = "eqL06:Out" input = "eqL07:In" }
          { output = "eqL07:Out" input = "eqL08:In" }
          { output = "eqL08:Out" input = "eqL09:In" }
          { output = "eqL09:Out" input = "eqL10:In" }
          { output = "eqL10:Out" input = "eqL11:In" }
          { output = "eqL11:Out" input = "eqL12:In" }
          { output = "eqL12:Out" input = "eqL13:In" }
          { output = "eqL13:Out" input = "eqL14:In" }
          { output = "eqL14:Out" input = "eqL15:In" }
          { output = "eqL15:Out" input = "eqL16:In" }

          # Right EQ chain (16 peaking filters in series)
          { output = "balance_right:Out" input = "eqR01:In" }
          { output = "eqR01:Out" input = "eqR02:In" }
          { output = "eqR02:Out" input = "eqR03:In" }
          { output = "eqR03:Out" input = "eqR04:In" }
          { output = "eqR04:Out" input = "eqR05:In" }
          { output = "eqR05:Out" input = "eqR06:In" }
          { output = "eqR06:Out" input = "eqR07:In" }
          { output = "eqR07:Out" input = "eqR08:In" }
          { output = "eqR08:Out" input = "eqR09:In" }
          { output = "eqR09:Out" input = "eqR10:In" }
          { output = "eqR10:Out" input = "eqR11:In" }
          { output = "eqR11:Out" input = "eqR12:In" }
          { output = "eqR12:Out" input = "eqR13:In" }
          { output = "eqR13:Out" input = "eqR14:In" }
          { output = "eqR14:Out" input = "eqR15:In" }
          { output = "eqR15:Out" input = "eqR16:In" }
        ]
        inputs  = [ "in_left:In" "in_right:In" ]
        outputs = [ "eqL16:Out" "eqR16:Out" ]
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
            # Look for monostereo, balance, and EQ node controls
            m_string = re.match(r'^String\s+"((monostereo_|balance_|eqL\d+:|eqR\d+:).+)"$', raw)
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
                m_legacy = re.match(r'"?((monostereo_|balance_|eqL\d+:|eqR\d+:).+)"?\s*=\s*([0-9]+(?:\.[0-9]+)?)', raw)
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
    """Set monostereo mode: stereo, mono, left, right.
    
    Args:
        mode: Channel mixing mode ('mono', 'stereo', 'left', 'right')
        
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
    else:
        logger.error("Invalid monostereo mode: %s (use stereo|mono|left|right)", mode)
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
    
    # Extract balance gains (missing gains are treated as 0.0)
    bL1 = gains.get("balance_left:Gain_1", 0.0)
    bL2 = gains.get("balance_left:Gain_2", 0.0)
    bR1 = gains.get("balance_right:Gain_1", 0.0)
    bR2 = gains.get("balance_right:Gain_2", 0.0)
    
    tol = 0.02
    def eq(x, y):
        return abs(x - y) <= tol
    
    # Check for perfect center/bypass case first
    if eq(bL1, 1.0) and eq(bL2, 0.0) and eq(bR1, 0.0) and eq(bR2, 1.0):
        return 0.0
    
    # The balance math with normalization:
    # Original: bL1 = 1 - B/2, bL2 = -B/2, bR1 = -B/2, bR2 = 1 + B/2  
    # Normalized by max_gain to keep all gains <= 1.0
    # So we need to reverse this process.
    
    # Check if crossfeed gains are equal (they should be after normalization)
    if eq(bL2, bR1) and (bL1 > 0 or bR2 > 0):  # At least one main gain should be non-zero
        # Find the normalization factor by looking at the maximum expected gain
        # For balance B, max expected gain is max(1 - B/2, 1 + B/2, |B/2|)
        
        # Try different balance values to see which one produces the observed pattern
        for test_balance in [-1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 
                            0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            # Calculate expected gains
            expected_bL1 = 1 - test_balance/2
            expected_bL2 = -test_balance/2  
            expected_bR1 = -test_balance/2
            expected_bR2 = 1 + test_balance/2
            
            # Apply normalization like the setter does
            max_gain = max(abs(expected_bL1), abs(expected_bL2), abs(expected_bR1), abs(expected_bR2))
            if max_gain > 1.0:
                expected_bL1 /= max_gain
                expected_bL2 /= max_gain
                expected_bR1 /= max_gain  
                expected_bR2 /= max_gain
            
            # Negative gains become 0 in PipeWire
            if expected_bL2 < 0:
                expected_bL2 = 0
            if expected_bR1 < 0:
                expected_bR1 = 0
                
            # Check if this matches our observed gains
            if (eq(bL1, expected_bL1) and eq(bL2, expected_bL2) and 
                eq(bR1, expected_bR1) and eq(bR2, expected_bR2)):
                return round(test_balance, 6)
    
    # Special cases for extreme values
    # Full left (balance = -1): only left channel, right muted
    if eq(bR2, 0.0) and bL1 > 0 and eq(bL2, 0.0) and eq(bR1, 0.0):
        return -1.0
        
    # Full right (balance = 1): only right channel, left muted  
    if eq(bL1, 0.0) and eq(bL2, 0.0) and eq(bR1, 0.0) and bR2 > 0:
        return 1.0
    
    # Default to center if no pattern matches
    return 0.0

def get_eq(eq_num: int) -> Optional[Dict[str, float]]:
    """Get frequency, Q, and gain for a specific EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        
    Returns:
        Dict with 'freq', 'q', 'gain' keys, or None if unavailable
    """
    if not 1 <= eq_num <= 16:
        return None
        
    gains = _get_mixer_status()
    if gains is None:
        return None
    
    # EQ parameters are stored as eqL01:Freq, eqL01:Q, eqL01:Gain (left channel as reference)
    # Format EQ number as zero-padded 2 digits
    eq_name = f"eqL{eq_num:02d}"
    freq_key = f"{eq_name}:Freq"
    q_key = f"{eq_name}:Q"
    gain_key = f"{eq_name}:Gain"
    
    # Default EQ values from the filter-chain configuration
    default_freqs = [32.0, 50.0, 80.0, 125.0, 200.0, 315.0, 500.0, 800.0,
                     1250.0, 2000.0, 3150.0, 5000.0, 8000.0, 10000.0, 16000.0, 20000.0]
    default_freq = default_freqs[eq_num - 1] if eq_num <= len(default_freqs) else 1000.0
    
    return {
        'freq': gains.get(freq_key, default_freq),
        'q': gains.get(q_key, 1.0),
        'gain': gains.get(gain_key, 0.0)  # 0dB default
    }

def get_eq_left(eq_num: int) -> Optional[Dict[str, float]]:
    """Get frequency, Q, and gain for a specific left channel EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        
    Returns:
        Dict with 'freq', 'q', 'gain' keys, or None if unavailable
    """
    return _get_eq_channel(eq_num, 'L')

def get_eq_right(eq_num: int) -> Optional[Dict[str, float]]:
    """Get frequency, Q, and gain for a specific right channel EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        
    Returns:
        Dict with 'freq', 'q', 'gain' keys, or None if unavailable
    """
    return _get_eq_channel(eq_num, 'R')

def _get_eq_channel(eq_num: int, channel: str) -> Optional[Dict[str, float]]:
    """Get frequency, Q, and gain for a specific EQ filter channel.
    
    Args:
        eq_num: EQ filter number (1-16)
        channel: 'L' for left or 'R' for right
        
    Returns:
        Dict with 'freq', 'q', 'gain' keys, or None if unavailable
    """
    if not 1 <= eq_num <= 16:
        return None
        
    gains = _get_mixer_status()
    if gains is None:
        return None
    
    # Format EQ number as zero-padded 2 digits
    eq_name = f"eq{channel}{eq_num:02d}"
    freq_key = f"{eq_name}:Freq"
    q_key = f"{eq_name}:Q"
    gain_key = f"{eq_name}:Gain"
    
    # Default EQ values from the filter-chain configuration
    default_freqs = [32.0, 50.0, 80.0, 125.0, 200.0, 315.0, 500.0, 800.0,
                     1250.0, 2000.0, 3150.0, 5000.0, 8000.0, 10000.0, 16000.0, 20000.0]
    default_freq = default_freqs[eq_num - 1] if eq_num <= len(default_freqs) else 1000.0
    
    return {
        'freq': gains.get(freq_key, default_freq),
        'q': gains.get(q_key, 1.0),
        'gain': gains.get(gain_key, 0.0)
    }

def get_eq_all() -> Optional[Dict[int, Dict[str, float]]]:
    """Get frequency, Q, and gain for all EQ filters.
    
    Returns:
        Dict mapping EQ numbers (1-16) to dicts with freq/q/gain, or None if unavailable
    """
    gains = _get_mixer_status()
    if gains is None:
        return None
        
    eq_filters = {}
    default_freqs = [32.0, 50.0, 80.0, 125.0, 200.0, 315.0, 500.0, 800.0,
                     1250.0, 2000.0, 3150.0, 5000.0, 8000.0, 10000.0, 16000.0, 20000.0]
    
    for eq_num in range(1, 17):
        # Format EQ number as zero-padded 2 digits
        eq_name = f"eqL{eq_num:02d}"
        freq_key = f"{eq_name}:Freq"
        q_key = f"{eq_name}:Q"
        gain_key = f"{eq_name}:Gain"
        
        default_freq = default_freqs[eq_num - 1] if eq_num <= len(default_freqs) else 1000.0
        
        eq_filters[eq_num] = {
            'freq': gains.get(freq_key, default_freq),
            'q': gains.get(q_key, 1.0),
            'gain': gains.get(gain_key, 0.0)
        }
        
    return eq_filters

def set_eq(eq_num: int, freq: Optional[float] = None, q: Optional[float] = None, 
           gain: Optional[float] = None, *, node_name: Optional[str] = None, 
           node_id: Optional[Union[str,int]] = None) -> bool:
    """Set frequency, Q, and/or gain for a specific EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        freq: Frequency in Hz (optional, keeps current if None)
        q: Q factor (optional, keeps current if None)  
        gain: Gain in dB (optional, keeps current if None)
        
    Returns:
        True if successful, False otherwise
    """
    if not 1 <= eq_num <= 16:
        return False
        
    # Get current values if we're only updating some parameters
    current = get_eq(eq_num)
    if current is None:
        return False
        
    # Use current values for parameters not being changed
    if freq is None:
        freq = current['freq']
    if q is None:
        q = current['q'] 
    if gain is None:
        gain = current['gain']
        
    # Validate parameters
    try:
        freq_val = float(freq)
        q_val = float(q)
        gain_val = float(gain)
        
        if freq_val <= 0 or freq_val > 24000:
            return False  # Invalid frequency range
        if q_val <= 0 or q_val > 20:
            return False  # Invalid Q range
        if gain_val < -15 or gain_val > 15:
            return False  # Invalid gain range
    except ValueError:
        return False
        
    return _apply_eq_filter(eq_num, freq_val, q_val, gain_val)

def set_eq_left(eq_num: int, freq: Optional[float] = None, q: Optional[float] = None, 
                gain: Optional[float] = None, *, node_name: Optional[str] = None, 
                node_id: Optional[Union[str,int]] = None) -> bool:
    """Set frequency, Q, and/or gain for a specific left channel EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        freq: Frequency in Hz (optional, keeps current if None)
        q: Q factor (optional, keeps current if None)  
        gain: Gain in dB (optional, keeps current if None)
        
    Returns:
        True if successful, False otherwise
    """
    return _set_eq_channel(eq_num, 'L', freq, q, gain)

def set_eq_right(eq_num: int, freq: Optional[float] = None, q: Optional[float] = None, 
                 gain: Optional[float] = None, *, node_name: Optional[str] = None, 
                 node_id: Optional[Union[str,int]] = None) -> bool:
    """Set frequency, Q, and/or gain for a specific right channel EQ filter (1-16).
    
    Args:
        eq_num: EQ filter number (1-16)
        freq: Frequency in Hz (optional, keeps current if None)
        q: Q factor (optional, keeps current if None)  
        gain: Gain in dB (optional, keeps current if None)
        
    Returns:
        True if successful, False otherwise
    """
    return _set_eq_channel(eq_num, 'R', freq, q, gain)

def _set_eq_channel(eq_num: int, channel: str, freq: Optional[float] = None, 
                    q: Optional[float] = None, gain: Optional[float] = None) -> bool:
    """Set frequency, Q, and/or gain for a specific EQ filter channel.
    
    Args:
        eq_num: EQ filter number (1-16)
        channel: 'L' for left or 'R' for right
        freq: Frequency in Hz (optional, keeps current if None)
        q: Q factor (optional, keeps current if None)  
        gain: Gain in dB (optional, keeps current if None)
        
    Returns:
        True if successful, False otherwise
    """
    if not 1 <= eq_num <= 16:
        return False
        
    # Get current values if we're only updating some parameters
    current = _get_eq_channel(eq_num, channel)
    if current is None:
        return False
        
    # Use current values for parameters not being changed
    if freq is None:
        freq = current['freq']
    if q is None:
        q = current['q'] 
    if gain is None:
        gain = current['gain']
        
    # Validate parameters
    try:
        freq_val = float(freq)
        q_val = float(q)
        gain_val = float(gain)
        
        if freq_val <= 0 or freq_val > 24000:
            return False  # Invalid frequency range
        if q_val <= 0 or q_val > 20:
            return False  # Invalid Q range
        if gain_val < -15 or gain_val > 15:
            return False  # Invalid gain range
    except ValueError:
        return False
        
    return _apply_eq_filter_channel(eq_num, channel, freq_val, q_val, gain_val)

def set_eq_all(eq_filters: Dict[int, Dict[str, float]], *, node_name: Optional[str] = None, 
               node_id: Optional[Union[str,int]] = None) -> bool:
    """Set frequency, Q, and gain for multiple EQ filters.
    
    Args:
        eq_filters: Dict mapping EQ numbers (1-16) to dicts with freq/q/gain values
        
    Returns:
        True if successful, False otherwise
    """
    # Validate all EQ filters first
    for eq_num, params in eq_filters.items():
        if not 1 <= eq_num <= 16:
            return False
        if not isinstance(params, dict):
            return False
        
        for key in ['freq', 'q', 'gain']:
            if key not in params:
                return False
            try:
                val = float(params[key])
                if key == 'freq' and (val <= 0 or val > 24000):
                    return False
                elif key == 'q' and (val <= 0 or val > 20):
                    return False
                elif key == 'gain' and (val < -15 or val > 15):
                    return False
            except ValueError:
                return False
            
    return _apply_eq_filters(eq_filters)

def _apply_eq_filter_channel(eq_num: int, channel: str, freq: float, q: float, gain: float) -> bool:
    """Apply freq, Q, and gain to a specific EQ filter channel."""
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
        
    # Format EQ number as zero-padded 2 digits
    eq_name = f"eq{channel}{eq_num:02d}"
    
    # Set parameters for the specified channel
    param = '{ "params": [ "%s:Freq" %0.2f "%s:Q" %0.6f "%s:Gain" %0.2f ] }' % (
        eq_name, freq, eq_name, q, eq_name, gain)
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
        # Update cache
        _last_mixer_gains.update({
            f"{eq_name}:Freq": freq,
            f"{eq_name}:Q": q,
            f"{eq_name}:Gain": gain,
        })
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying EQ filter: %s", e)
    return False

def _apply_eq_filter(eq_num: int, freq: float, q: float, gain: float) -> bool:
    """Apply freq, Q, and gain to a specific EQ filter."""
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
        
    # Format EQ number as zero-padded 2 digits
    eq_left = f"eqL{eq_num:02d}"
    eq_right = f"eqR{eq_num:02d}"
    
    # Set the same parameters for both left and right channels
    param = '{ "params": [ "%s:Freq" %0.2f "%s:Q" %0.6f "%s:Gain" %0.2f "%s:Freq" %0.2f "%s:Q" %0.6f "%s:Gain" %0.2f ] }' % (
        eq_left, freq, eq_left, q, eq_left, gain,
        eq_right, freq, eq_right, q, eq_right, gain)
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
        # Update cache
        _last_mixer_gains.update({
            f"{eq_left}:Freq": freq,
            f"{eq_left}:Q": q,
            f"{eq_left}:Gain": gain,
            f"{eq_right}:Freq": freq,
            f"{eq_right}:Q": q,
            f"{eq_right}:Gain": gain,
        })
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying EQ filter: %s", e)
    return False

def _apply_eq_filters(eq_filters: Dict[int, Dict[str, float]]) -> bool:
    """Apply freq, Q, and gain to multiple EQ filters in one operation."""
    nid = _resolve_mixer_container_node()
    if nid is None:
        logger.error("Mixer container node '%s' not found", DEFAULT_MIXER_NODE_NAME)
        return False
        
    # Build parameter string for all specified EQ filters
    params = []
    cache_updates = {}
    for eq_num, eq_params in eq_filters.items():
        freq = eq_params['freq']
        q = eq_params['q'] 
        gain = eq_params['gain']
        
        # Format EQ number as zero-padded 2 digits
        eq_left = f"eqL{eq_num:02d}"
        eq_right = f"eqR{eq_num:02d}"
        
        params.extend([
            f'"{eq_left}:Freq" {freq:0.2f}',
            f'"{eq_left}:Q" {q:0.6f}',
            f'"{eq_left}:Gain" {gain:0.2f}',
            f'"{eq_right}:Freq" {freq:0.2f}',
            f'"{eq_right}:Q" {q:0.6f}',
            f'"{eq_right}:Gain" {gain:0.2f}'
        ])
        cache_updates.update({
            f"{eq_left}:Freq": freq,
            f"{eq_left}:Q": q,
            f"{eq_left}:Gain": gain,
            f"{eq_right}:Freq": freq,
            f"{eq_right}:Q": q,
            f"{eq_right}:Gain": gain,
        })
        
    param = '{ "params": [ ' + ' '.join(params) + ' ] }'
    try:
        res = subprocess.run(["pw-cli", "set-param", str(nid), "Props", param], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("pw-cli set-param failed: %s", res.stderr.strip())
            return False
        # Update cache
        _last_mixer_gains.update(cache_updates)
        return True
    except FileNotFoundError:
        logger.error("pw-cli not found")
    except Exception as e:
        logger.error("Error applying EQ filters: %s", e)
    return False

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
        print("  config-pipewire get-default-volume       # get default sink volume")
        print("  config-pipewire get-default-volume-db    # get default sink volume in dB")
        print("  config-pipewire set-default-volume <vol> # set default sink volume")
        print("  config-pipewire set-default-volume-db <vol_db> # set default sink volume in dB")
        print("  config-pipewire mixer-status")
        print("  config-pipewire mixer-gains        # show individual gain values (live or cached)")
        print("  config-pipewire get-monostereo     # get current monostereo mode")
        print("  config-pipewire get-balance        # get current balance value")
        print("  config-pipewire get-eq <eq_num> [channel]    # get EQ filter parameters (1-16), channel: left/right/both")
        print("  config-pipewire get-eq-all         # get all EQ filter parameters")
        print("  config-pipewire mixer-save         # save current mixer state")
        print("  config-pipewire mixer-restore      # restore saved mixer state")
        print("  config-pipewire monostereo <mode>  # set monostereo mode")
        print("  config-pipewire balance <B>        # set balance")
        print("  config-pipewire eq <eq_num> <freq> <q> <gain> [channel]  # set EQ filter parameters, channel: left/right/both")
        print("  config-pipewire eq-reset           # reset all EQ filters to defaults")
        print("")
        print("  control_name: either 'node_id:device_name' or just 'node_id'")
        print("  volume: linear volume (0.0 - 1.0)")
        print("  volume_db: volume in decibels (e.g., -20.0)")
        print("  mode: stereo, mono, left, right")
        print("  B: balance in [-1,1]; -1 full left, 0 center, +1 full right")
        print("  eq_num: EQ filter number (1-16)")
        print("  freq: frequency in Hz (20-20000)")
        print("  q: Q factor (0.1-20.0)")
        print("  gain: gain in dB (-15.0 to +15.0)")
        print("  channel: left, right, both (default: both)")
        print("  examples:")
        print("    config-pipewire monostereo stereo         # set stereo mode")
        print("    config-pipewire balance -0.3              # set left bias")
        print("    config-pipewire get-monostereo            # get current mode")
        print("    config-pipewire get-balance               # get current balance")
        print("    config-pipewire get-default-volume        # get current default sink volume")
        print("    config-pipewire set-default-volume 0.8    # set default sink to 80%")
        print("    config-pipewire set-default-volume-db -6  # set default sink to -6dB")
        print("    config-pipewire eq 1 80.0 1.5 -3.0       # set EQ 1: 80Hz, Q=1.5, -3dB (both channels)")
        print("    config-pipewire eq 5 1250.0 0.8 +2.5     # set EQ 5: 1.25kHz, Q=0.8, +2.5dB (both channels)")
        print("    config-pipewire eq 3 200.0 2.0 +1.0 left # set left EQ 3: 200Hz, Q=2.0, +1dB")
        print("    config-pipewire eq 3 250.0 1.8 +0.5 right # set right EQ 3: 250Hz, Q=1.8, +0.5dB")
        print("    config-pipewire get-eq 3                 # get EQ 3 parameters (both channels)")
        print("    config-pipewire get-eq 3 left            # get left EQ 3 parameters")
        print("    config-pipewire get-eq 3 right           # get right EQ 3 parameters")
        print("    config-pipewire get-eq-all               # show all EQ filters")

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
    elif cmd == "get-eq" and len(sys.argv) >= 3:
        try:
            eq_num = int(sys.argv[2])
            if not 1 <= eq_num <= 16:
                print("EQ filter number must be between 1 and 16")
                sys.exit(3)
        except ValueError:
            print("EQ filter number must be a number between 1 and 16")
            sys.exit(3)
        
        # Optional channel parameter
        channel = sys.argv[3].lower() if len(sys.argv) > 3 else "both"
        
        if channel == "left":
            eq_params = get_eq_left(eq_num)
            if eq_params is None:
                print("EQ status unavailable")
                sys.exit(2)
            print(f"EQ Left {eq_num}: freq={eq_params['freq']:0.1f}Hz, Q={eq_params['q']:0.2f}, gain={eq_params['gain']:+0.1f}dB")
        elif channel == "right":
            eq_params = get_eq_right(eq_num)
            if eq_params is None:
                print("EQ status unavailable")
                sys.exit(2)
            print(f"EQ Right {eq_num}: freq={eq_params['freq']:0.1f}Hz, Q={eq_params['q']:0.2f}, gain={eq_params['gain']:+0.1f}dB")
        elif channel == "both":
            # Show both channels
            eq_left = get_eq_left(eq_num)
            eq_right = get_eq_right(eq_num)
            if eq_left is None or eq_right is None:
                print("EQ status unavailable")
                sys.exit(2)
            print(f"EQ Left  {eq_num}: freq={eq_left['freq']:0.1f}Hz, Q={eq_left['q']:0.2f}, gain={eq_left['gain']:+0.1f}dB")
            print(f"EQ Right {eq_num}: freq={eq_right['freq']:0.1f}Hz, Q={eq_right['q']:0.2f}, gain={eq_right['gain']:+0.1f}dB")
        else:
            print("Channel must be 'left', 'right', or 'both'")
            sys.exit(3)
    elif cmd == "get-eq-all":
        eq_filters = get_eq_all()
        if eq_filters is None:
            print("EQ status unavailable")
            sys.exit(2)
        for eq_num in range(1, 17):
            params = eq_filters[eq_num]
            print(f"EQ {eq_num:2d}: freq={params['freq']:6.1f}Hz, Q={params['q']:4.2f}, gain={params['gain']:+5.1f}dB")
    elif cmd == "eq" and len(sys.argv) >= 6:
        try:
            eq_num = int(sys.argv[2])
            freq = float(sys.argv[3])
            q = float(sys.argv[4])
            gain = float(sys.argv[5])
            if not 1 <= eq_num <= 16:
                print("EQ filter number must be between 1 and 16")
                sys.exit(3)
            if not 20 <= freq <= 20000:
                print("Frequency must be between 20 and 20000 Hz")
                sys.exit(3)
            if not 0.1 <= q <= 20.0:
                print("Q factor must be between 0.1 and 20.0")
                sys.exit(3)
            if not -15.0 <= gain <= 15.0:
                print("Gain must be between -15.0 and +15.0 dB")
                sys.exit(3)
        except ValueError:
            print("EQ parameters must be numeric: eq <eq_num> <freq> <q> <gain> [channel]")
            sys.exit(3)
        
        # Optional channel parameter
        channel = sys.argv[6].lower() if len(sys.argv) > 6 else "both"
        
        if channel == "left":
            if not set_eq_left(eq_num, freq, q, gain):
                print("Failed to set left EQ filter")
                sys.exit(4)
        elif channel == "right":
            if not set_eq_right(eq_num, freq, q, gain):
                print("Failed to set right EQ filter")
                sys.exit(4)
        elif channel == "both":
            if not set_eq(eq_num, freq, q, gain):
                print("Failed to set EQ filter")
                sys.exit(4)
        else:
            print("Channel must be 'left', 'right', or 'both'")
            sys.exit(3)
        print("OK")
    elif cmd == "eq-reset":
        # Reset all EQ filters to defaults
        default_freqs = [32.0, 50.0, 80.0, 125.0, 200.0, 315.0, 500.0, 800.0,
                         1250.0, 2000.0, 3150.0, 5000.0, 8000.0, 10000.0, 16000.0, 20000.0]
        reset_filters = {}
        for eq_num in range(1, 17):
            reset_filters[eq_num] = {
                'freq': default_freqs[eq_num - 1] if eq_num <= len(default_freqs) else 1000.0,
                'q': 1.0,
                'gain': 0.0
            }
        if not set_eq_all(reset_filters):
            print("Failed to reset EQ")
            sys.exit(4)
        print("OK")
    elif cmd == "get-default-volume":
        default_sink = get_default_sink()
        if default_sink:
            vol = get_volume(default_sink)
            if vol is None:
                print("Failed to get default sink volume")
                sys.exit(2)
            print(f"{vol:.6f}")
        else:
            print("No default sink found")
            sys.exit(2)
    elif cmd == "get-default-volume-db":
        default_sink = get_default_sink()
        if default_sink:
            vol_db = get_volume_db(default_sink)
            if vol_db is None:
                print("Failed to get default sink volume")
                sys.exit(2)
            if vol_db == -math.inf:
                print("-inf")
            else:
                print(f"{vol_db:.2f}")
        else:
            print("No default sink found")
            sys.exit(2)
    elif cmd == "set-default-volume" and len(sys.argv) == 3:
        default_sink = get_default_sink()
        if not default_sink:
            print("No default sink found")
            sys.exit(2)
        try:
            volume = float(sys.argv[2])
            if volume < 0.0 or volume > 1.0:
                print("Volume must be between 0.0 and 1.0")
                sys.exit(3)
        except ValueError:
            print("Volume must be a float between 0.0 and 1.0")
            sys.exit(3)
        ok = set_volume(default_sink, volume)
        if not ok:
            print("Failed to set default sink volume")
            sys.exit(4)
        print("OK")
    elif cmd == "set-default-volume-db" and len(sys.argv) == 3:
        default_sink = get_default_sink()
        if not default_sink:
            print("No default sink found")
            sys.exit(2)
        try:
            volume_db = float(sys.argv[2])
        except ValueError:
            print("Volume in dB must be a float (e.g., -20.0)")
            sys.exit(3)
        ok = set_volume_db(default_sink, volume_db)
        if not ok:
            print("Failed to set default sink volume")
            sys.exit(4)
        print("OK")
    else:
        print_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
