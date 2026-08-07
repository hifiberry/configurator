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

# --- PEM private-key blocks --------------------------------------------
#
# These are not handled with a single regex over the whole text. A PEM block
# reaches the report in several shapes -- plain, indented, or with a
# journalctl prefix ("Aug 07 10:00:01 host sshd[123]: ") in front of every
# line -- and the text may also contain a BEGIN marker whose END marker was
# cut off by a truncated log excerpt. A single pattern either misses the
# prefixed shapes or, with an open-ended body match, eats the rest of the
# report. So the block is walked line by line instead (see
# _redact_pem_keys), with one hard rule: every input line produces exactly
# one output line. Key material is *replaced*, never deleted.

_PEM_BEGIN = re.compile(r"(?i)-----BEGIN [^\n-]*PRIVATE KEY-----")
_PEM_END = re.compile(r"(?i)-----END [^\n-]*PRIVATE KEY-----")

# Leading noise on a line that cannot itself be key material: indentation
# and/or a log prefix. A prefix is simply "everything up to the last ': '",
# with no assumption about how many fields it holds -- journalctl writes
# anything from "sshd[123]: " to "Aug 07 10:00:01 host sshd[123]: "
# depending on its output format and flags, and counting fields silently
# missed the shorter ones. Base64 never contains a colon, so this can never
# cut into key material; what it leaves is classified on its own merits
# below.
_LINE_PREFIX = re.compile(r"[ \t]*(?:.*:[ \t]+)?")

# A PEM body line: base64 with padding only at the very end. Excluding "="
# from the middle is what keeps "password=hunter2" from looking like key
# material when it follows an unterminated block.
_BASE64_LINE = re.compile(r"[A-Za-z0-9+/]+={0,2}")

# RFC 1421 headers of an encrypted key; they sit between the BEGIN marker
# and the base64 body and must not be read as the end of the block.
_PEM_HEADER = re.compile(r"(?i)(?:Proc-Type|DEK-Info):")


def _split_line(line: str) -> tuple:
    """Split a line into its non-secret prefix and the payload after it."""
    cut = _LINE_PREFIX.match(line).end()
    return line[:cut], line[cut:].strip()


def _redact_payload(line: str) -> str:
    """Keep the line's prefix, replace whatever follows it."""
    prefix, payload = _split_line(line)
    return prefix + REDACTED if payload else line


def _is_key_body(line: str, payload: str, seen_body: bool) -> bool:
    """Does this line still look like part of a PEM body?

    Only consulted for a block with no END marker, where the body's extent
    has to be guessed. The guess errs towards stopping early for anything
    that does not look like key material, because the alternative is
    swallowing report content.
    """
    # Searched in the whole line, not in the payload: a header's own colon
    # is what _LINE_PREFIX strips off, and the header may itself be behind
    # a log prefix.
    if _PEM_HEADER.search(line):
        return True
    if not payload:
        # The blank line separating encrypted-key headers from the body;
        # once the base64 body has started, a blank line ends the block.
        return not seen_body
    return _BASE64_LINE.fullmatch(payload) is not None


def _redact_pem_keys(text: str) -> str:
    """Replace the body of every PEM private-key block in text.

    A block that has an END marker somewhere after it is redacted up to
    that marker, whatever its lines look like. A block without one is
    redacted only as far as the lines still look like key material, so the
    diagnostics that follow a truncated block survive.
    """
    if not _PEM_BEGIN.search(text):
        return text

    lines = text.split("\n")
    count = len(lines)

    # Index of the next line from i onwards holding a BEGIN / an END marker.
    # A block counts as terminated only if its END marker comes before the
    # next BEGIN marker -- otherwise that END belongs to a later block and
    # this one is truncated.
    next_begin = [None] * (count + 1)
    next_end = [None] * (count + 1)
    for i in range(count - 1, -1, -1):
        next_begin[i] = i if _PEM_BEGIN.search(lines[i]) else next_begin[i + 1]
        next_end[i] = i if _PEM_END.search(lines[i]) else next_end[i + 1]

    out = []
    i = 0
    while i < count:
        line = lines[i]
        i += 1
        begin = _PEM_BEGIN.search(line)
        if begin is None:
            out.append(line)
            continue

        # Everything before the BEGIN marker is a prefix and stays; anything
        # after it on the same line is key material.
        head, rest = line[: begin.end()], line[begin.end():]
        end = _PEM_END.search(rest)
        if end is not None:
            # Whole block squeezed onto one line.
            out.append(head + _redact_payload(rest[: end.start()]) + rest[end.start():])
            continue
        out.append(head + (REDACTED if rest.strip() else ""))

        end_at, begin_at = next_end[i], next_begin[i]
        terminated = end_at is not None and (begin_at is None or end_at < begin_at)
        seen_body = False
        while i < count:
            line = lines[i]
            end = _PEM_END.search(line)
            if end is not None:
                out.append(_redact_payload(line[: end.start()]) + line[end.start():])
                i += 1
                break
            _, payload = _split_line(line)
            if not terminated and not _is_key_body(line, payload, seen_body):
                break
            out.append(_redact_payload(line))
            if payload and not _PEM_HEADER.search(line):
                seen_body = True
            i += 1

    return "\n".join(out)


def redact_secrets(text: str) -> str:
    """Replace secret values in text with REDACTED.

    Handles four shapes: key/value pairs (password=..., psk: "...", and
    compound identifiers like WPA_PSK=... or AWS_SECRET_ACCESS_KEY=...),
    credentials embedded in URLs (smb://user:pass@host), HTTP
    "Authorization: Bearer <token>" headers, and PEM private-key blocks
    (the body between a "-----BEGIN ... PRIVATE KEY-----" marker and its
    matching "-----END" marker -- or, if the block was truncated, e.g. by a
    log excerpt that cuts off mid-key, as far as the lines look like key
    material). PEM blocks are recognised no matter what precedes them on
    the line, so journalctl-prefixed and indented blocks are covered too;
    content that follows a truncated block is left untouched.
    """
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}:{REDACTED}@", text)
    text = _BEARER_TOKEN.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _redact_pem_keys(text)
    return text
