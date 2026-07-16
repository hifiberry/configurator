#!/usr/bin/env python3
"""Parse apt's APT::Status-Fd progress channel.

apt writes machine-readable progress to a dedicated fd, e.g.

    dlstatus:1:20.0:Retrieving hifiberry-tidal-connect
    pmstatus:hifiberry-tidal-connect:50.0:Unpacking

which is how we report a real percentage rather than a fake bar.
"""

from typing import Optional, Tuple

from .jobs import PHASE_CONFIGURING, PHASE_DOWNLOADING, PHASE_INSTALLING

_CONFIGURING_PREFIXES = ("setting up", "configuring")


def parse_status_line(line: str) -> Optional[Tuple[str, float, str]]:
    """Return (phase, percent, message), or None for lines we don't act on."""
    if not line:
        return None

    # Message may contain colons, so split only the first three fields.
    parts = line.strip().split(":", 3)
    if len(parts) != 4:
        return None

    kind, _subject, raw_percent, message = parts

    if kind not in ("dlstatus", "pmstatus"):
        return None

    try:
        percent = float(raw_percent)
    except ValueError:
        return None

    if kind == "dlstatus":
        phase = PHASE_DOWNLOADING
    elif message.strip().lower().startswith(_CONFIGURING_PREFIXES):
        phase = PHASE_CONFIGURING
    else:
        phase = PHASE_INSTALLING

    return phase, percent, message
