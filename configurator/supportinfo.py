"""
config-supportinfo - collect a redacted diagnostic report for bug reports.

The output of this tool is meant to be pasted into public GitHub issues, so
everything it prints passes through redact_secrets() first.
"""

import re

REDACTED = "***REDACTED***"

# Base secret words. The key-value pattern below wraps these in optional
# leading/trailing identifier characters so it matches compound identifiers
# that merely *contain* one of these words (WPA_PSK, AWS_SECRET_ACCESS_KEY,
# secret_key, ...), not only identifiers equal to one of them. Over-matching
# (e.g. redacting "secretary=x") is the accepted cost of that: a missed
# secret is worse than an over-redacted harmless field.
_SECRET_KEYS = (
    r"password|passwd|psk|passphrase|secret|token|api[_-]?key|"
    r"credential|credentials"
)

_KEY_VALUE = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:" + _SECRET_KEYS + r")[A-Za-z0-9_.-]*)"
    r"([\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;\"']+)"
)

_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):([^\s@]+)@")

_BEARER_TOKEN = re.compile(r"(?i)\b(Authorization\s*:\s*Bearer\s+)([^\s,;\"']+)")

_PEM_PRIVATE_KEY = re.compile(
    r"(?is)(-----BEGIN [^\n-]*PRIVATE KEY-----)(.*?)(-----END [^\n-]*PRIVATE KEY-----|\Z)"
)


def redact_secrets(text: str) -> str:
    """Replace secret values in text with REDACTED.

    Handles four shapes: key/value pairs (password=..., psk: "...", and
    compound identifiers like WPA_PSK=... or AWS_SECRET_ACCESS_KEY=...),
    credentials embedded in URLs (smb://user:pass@host), HTTP
    "Authorization: Bearer <token>" headers, and PEM private-key blocks
    (everything between a "-----BEGIN ... PRIVATE KEY-----" marker and its
    matching "-----END" marker, or the end of the text if the block was
    truncated, e.g. by a log excerpt that cuts off mid-key).
    """
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}:{REDACTED}@", text)
    text = _BEARER_TOKEN.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _PEM_PRIVATE_KEY.sub(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", text)
    return text
