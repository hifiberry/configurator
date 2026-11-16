"""Read and set which audio server the device runs: PipeWire or aas.

The switch itself is done by the hifiberry-audio-server command that the aas
package ships. Most devices do not have it, and then only PipeWire exists.
"""

import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

COMMAND = "/usr/sbin/hifiberry-audio-server"
CHOICE_PATH = "/etc/hifiberry/audio-server"
STATE_PATH = "/var/lib/aas/state.toml"

# Written by a factory reset that could not reach pipewire-api because aas
# was in charge; the next config server start retries the PipeWire reset.
PIPEWIRE_RESET_MARKER = "/var/lib/hifiberry/pipewire-reset-pending"
PIPEWIRE_RESET_INTERVAL = 5
PIPEWIRE_RESET_LIMIT = 180

SERVERS = ("pipewire", "aas")

# Serialises set_server() and reset(): both rewrite the choice and the state.
_lock = threading.Lock()


class AudioServerUnavailable(Exception):
    """The hifiberry-audio-server command is not installed."""


class AudioServerError(Exception):
    """The hifiberry-audio-server command failed."""


def chosen() -> str:
    """The server chosen for the next boot; anything unreadable means pipewire."""
    try:
        with open(CHOICE_PATH, "r", encoding="utf-8") as f:
            line = f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return "pipewire"
    return line if line == "aas" else "pipewire"


def available() -> bool:
    return os.access(COMMAND, os.X_OK)


def _running() -> str:
    return "aas" if _aas_active() else "pipewire"


def get() -> Dict[str, Any]:
    is_available = available()
    return {
        "running": _running() if is_available else "pipewire",
        "chosen": chosen(),
        "available": is_available,
    }


def set_server(server: str) -> Dict[str, Any]:
    """Choose the server for the next boot. Does not reboot."""
    if server not in SERVERS:
        raise ValueError(f"server must be one of: {', '.join(SERVERS)}")
    if not available():
        raise AudioServerUnavailable("aas is not installed on this device")
    with _lock:
        return _set_server(server)


def _set_server(server: str) -> Dict[str, Any]:
    try:
        result = subprocess.run([COMMAND, "set", server], capture_output=True,
                                text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise AudioServerError(
            f"{COMMAND} did not finish in time; the switch may be half done, "
            "choose the server again")
    except (OSError, subprocess.SubprocessError) as e:
        raise AudioServerError(f"{COMMAND} could not run: {e}")
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        raise AudioServerError(stderr or (
            f"{COMMAND} exited with status {result.returncode}"))
    data = get()
    data["reboot_required"] = data["chosen"] != data["running"]
    data["warnings"] = stderr.splitlines() if stderr else []
    return data


def _systemctl(*args: str) -> None:
    result = subprocess.run(["systemctl", *args], capture_output=True,
                            text=True, timeout=30)
    if result.returncode != 0:
        message = (result.stderr or "").strip() or (
            f"systemctl {' '.join(args)} exited with status {result.returncode}")
        raise AudioServerError(message)


def _aas_active() -> bool:
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", "aas.service"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def reset(pipewire_reached: bool = True) -> Dict[str, Any]:
    """Part of the factory reset: drop aas's saved state, choose PipeWire.

    Best effort: a failing step is reported and the remaining ones still run.
    `pipewire_reached` says whether the PipeWire settings reset succeeded; when
    it did not and aas was in charge, PipeWire's saved settings would return
    after the reboot, so a marker makes the next start retry that reset.
    """
    if not available():
        return {"status": "unavailable", "reboot_required": False}
    with _lock:
        return _reset(pipewire_reached)


def _reset(pipewire_reached: bool) -> Dict[str, Any]:
    errors = []
    was_active = _aas_active()
    was_chosen = chosen() == "aas"

    def step(name, fn):
        try:
            fn()
            return True
        except Exception as e:
            logger.warning(f"audio server reset: {name} failed: {e}")
            errors.append(f"{name}: {e}")
            return False

    def remove_state():
        try:
            os.remove(STATE_PATH)
        except FileNotFoundError:
            pass

    def write_marker():
        os.makedirs(os.path.dirname(PIPEWIRE_RESET_MARKER), exist_ok=True)
        with open(PIPEWIRE_RESET_MARKER, "w", encoding="utf-8") as f:
            f.write("pending\n")

    stopped = True
    if was_active:
        stopped = step("stop aas.service", lambda: _systemctl("stop", "aas.service"))
    if stopped:
        step("remove saved state", remove_state)
    else:
        errors.append("remove saved state: skipped, aas.service was not stopped")
    if was_active:
        step("start aas.service", lambda: _systemctl("start", "aas.service"))
    switched = step("set pipewire", lambda: _set_server("pipewire"))
    if (was_active or was_chosen) and not pipewire_reached:
        step("mark pipewire reset pending", write_marker)

    reboot_required = bool(was_active and switched)
    if errors:
        return {"status": "error", "message": "; ".join(errors), "errors": errors,
                "reboot_required": reboot_required}
    return {"status": "success", "reboot_required": reboot_required}


def retry_pipewire_reset(reset_fn: Callable[[], Dict[str, Any]],
                         sleep: Callable[[float], None] = time.sleep,
                         interval: float = PIPEWIRE_RESET_INTERVAL,
                         limit: float = PIPEWIRE_RESET_LIMIT) -> bool:
    """Call reset_fn every `interval` s for up to `limit` s until it succeeds.

    On success the marker is removed. On giving up it stays for the next start.
    """
    waited = 0.0
    while True:
        try:
            result = reset_fn()
        except Exception as e:
            logger.warning(f"pending PipeWire reset failed: {e}")
            result = {}
        if result.get("status") == "success":
            try:
                os.remove(PIPEWIRE_RESET_MARKER)
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning(f"could not remove {PIPEWIRE_RESET_MARKER}: {e}")
            logger.info("pending PipeWire settings reset done")
            return True
        if waited >= limit:
            logger.warning("pending PipeWire settings reset not done, "
                           "will retry at the next start")
            return False
        sleep(interval)
        waited += interval


def start_pending_pipewire_reset(reset_fn: Callable[[], Dict[str, Any]],
                                 **kwargs) -> Optional[threading.Thread]:
    """If a factory reset left the marker, retry it in a daemon thread."""
    if not os.path.exists(PIPEWIRE_RESET_MARKER):
        return None
    thread = threading.Thread(target=retry_pipewire_reset, args=(reset_fn,),
                              kwargs=kwargs, name="pipewire-reset", daemon=True)
    thread.start()
    return thread
