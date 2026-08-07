"""
config-supportinfo - collect a redacted diagnostic report for bug reports.

The output of this tool is meant to be pasted into public GitHub issues, so
everything it prints passes through redact_secrets() first.
"""

import re

REDACTED = "***REDACTED***"

_SECRET_KEYS = (
    r"password|passwd|psk|secret|client[_-]?secret|token|api[_-]?key|"
    r"credential|credentials"
)

_KEY_VALUE = re.compile(
    r"(?i)\b(" + _SECRET_KEYS + r")([\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;\"']+)"
)

_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):([^\s@]+)@")


def redact_secrets(text: str) -> str:
    """Replace secret values in text with REDACTED.

    Handles two shapes: key/value pairs (password=..., psk: "...") and
    credentials embedded in URLs (smb://user:pass@host).
    """
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}:{REDACTED}@", text)
    return text
