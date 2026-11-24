"""Read and set aas's card latency in its local override file.

aas-config merges /etc/aas/aas.local.toml over the generated configuration at
boot. Only the top-level `latency_ms` key is touched, line by line, so the
comments and other settings in the file survive.
"""

import logging
import os
import re
import subprocess
import tempfile
import tomllib
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LOCAL_PATH = "/etc/aas/aas.local.toml"
KEY = "latency_ms"
MIN_LATENCY_MS = 1
MAX_LATENCY_MS = 100

_KEY_LINE = re.compile(r"^\s*" + KEY + r"\s*=")
_TABLE_LINE = re.compile(r"^\s*\[")


class AasSettingsFileError(Exception):
    """The local override file is not valid TOML."""


def _read_text() -> Optional[str]:
    try:
        with open(LOCAL_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as e:
        raise AasSettingsFileError(f"{LOCAL_PATH} is not valid UTF-8: {e}") from e


def _parse(text: str) -> Dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise AasSettingsFileError(f"{LOCAL_PATH} is not valid TOML: {e}") from e


def get() -> Dict[str, Optional[int]]:
    text = _read_text()
    if text is None:
        return {KEY: None}
    value = _parse(text).get(KEY)
    return {KEY: value if isinstance(value, int) and not isinstance(value, bool) else None}


def _edit(text: str, latency_ms: Optional[int]) -> str:
    lines: List[str] = text.splitlines()
    split = next((i for i, l in enumerate(lines) if _TABLE_LINE.match(l)), len(lines))
    top = [l for l in lines[:split] if not _KEY_LINE.match(l)]
    rest = lines[split:]
    if latency_ms is not None:
        new = f"{KEY} = {latency_ms}"
        last = max((i for i, l in enumerate(top) if l.strip()), default=-1)
        top.insert(last + 1, new)
        if rest and last + 2 == len(top):
            top.append("")  # keep a blank line before the first table
    out = "\n".join(top + rest)
    return out + "\n" if out else ""


def _aas_active() -> bool:
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", "aas.service"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _restart() -> None:
    # aas-config.service (oneshot, RemainAfterExit) merges the local file into
    # aas.toml and is not re-run by restarting aas.service alone, so restart
    # both in one transaction. --no-block: answer without waiting for aas.
    subprocess.run(["systemctl", "restart", "--no-block",
                    "aas-config.service", "aas.service"],
                   capture_output=True, text=True, timeout=30, check=True)


def set_latency(latency_ms: Optional[int]) -> Dict[str, Any]:
    if latency_ms is not None and (
            isinstance(latency_ms, bool) or not isinstance(latency_ms, int)
            or not MIN_LATENCY_MS <= latency_ms <= MAX_LATENCY_MS):
        raise ValueError(
            f"{KEY} must be an integer from {MIN_LATENCY_MS} to {MAX_LATENCY_MS} or null")
    text = _read_text() or ""
    _parse(text)
    new_text = _edit(text, latency_ms)
    _parse(new_text)

    directory = os.path.dirname(LOCAL_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aas.local.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(LOCAL_PATH):
            os.chmod(tmp, os.stat(LOCAL_PATH).st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, LOCAL_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    restarted = False
    if _aas_active():
        try:
            _restart()
            restarted = True
        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Restarting aas.service after the latency change failed: {e}")
    return {KEY: latency_ms, "restarted": restarted}
