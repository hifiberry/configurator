"""Read and set which audio server the device runs: PipeWire or aas.

The switch itself is done by the hifiberry-audio-server command that the aas
package ships. Most devices do not have it, and then only PipeWire exists.
"""

import logging
import os
import subprocess
from typing import Any, Dict

logger = logging.getLogger(__name__)

COMMAND = "/usr/sbin/hifiberry-audio-server"
CHOICE_PATH = "/etc/hifiberry/audio-server"
STATE_PATH = "/var/lib/aas/state.toml"

SERVERS = ("pipewire", "aas")


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
    try:
        result = subprocess.run([COMMAND, "get"], capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"{COMMAND} get failed: {e}")
        return "pipewire"
    if result.returncode != 0:
        return "pipewire"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "running":
            return parts[1] if parts[1] in SERVERS else "pipewire"
    return "pipewire"


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
    try:
        result = subprocess.run([COMMAND, "set", server], capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise AudioServerError(f"{COMMAND} could not run: {e}")
    if result.returncode != 0:
        message = (result.stderr or "").strip() or (
            f"{COMMAND} exited with status {result.returncode}")
        raise AudioServerError(message)
    data = get()
    data["reboot_required"] = data["chosen"] != data["running"]
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


def reset() -> Dict[str, Any]:
    """Part of the factory reset: drop aas's saved state, choose PipeWire.

    Best effort: a failing step is reported and the remaining ones still run.
    """
    if not available():
        return {"status": "unavailable"}

    errors = []
    was_active = _aas_active()

    def step(name, fn):
        try:
            fn()
        except (OSError, subprocess.SubprocessError, AudioServerError) as e:
            logger.warning(f"audio server reset: {name} failed: {e}")
            errors.append(f"{name}: {e}")

    def remove_state():
        try:
            os.remove(STATE_PATH)
        except FileNotFoundError:
            pass

    if was_active:
        step("stop aas.service", lambda: _systemctl("stop", "aas.service"))
    step("remove saved state", remove_state)
    if was_active:
        step("start aas.service", lambda: _systemctl("start", "aas.service"))
    step("set pipewire", lambda: set_server("pipewire"))

    if errors:
        return {"status": "error", "message": "; ".join(errors), "errors": errors}
    return {"status": "success"}
