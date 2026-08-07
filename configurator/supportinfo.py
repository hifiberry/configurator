"""
config-supportinfo - collect a redacted diagnostic report for bug reports.

The output of this tool is meant to be pasted into public GitHub issues, so
everything it prints passes through redact_secrets() first.
"""

import argparse
import json
import logging
import platform
import re
import subprocess
import sys

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


# --- Hardware and OS collectors -----------------------------------------
#
# Kept fields are selected by allowlist, not by excluding known-bad ones: a
# denylist silently leaks the next identifying field that get_flat_info_dict()
# grows (e.g. a MAC address or serial number) straight into a report that
# gets pasted into public GitHub issues. UUID, Hostname and Pretty Hostname
# are deliberately left off this allowlist -- the UUID is a stable device
# identifier and hostnames regularly contain people's real names, and
# neither helps debugging.

SAFE_SYSTEM_FIELDS = {"Pi Model", "Memory", "HAT", "Sound Card"}


def _flat_system_info() -> dict:
    """Indirection so tests can replace the hardware-dependent lookup."""
    from configurator.systeminfo import SystemInfo

    return SystemInfo().get_flat_info_dict()


def collect_system() -> dict:
    """Hardware description, without fields that identify the device or owner."""
    try:
        info = _flat_system_info()
    except Exception as e:
        return {"error": f"could not read system info: {e}"}
    return {k: v for k, v in info.items() if k in SAFE_SYSTEM_FIELDS}


def collect_os() -> dict:
    """Distribution, kernel and architecture."""
    pretty_name = "unknown"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    pretty_name = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass
    return {
        "OS": pretty_name,
        "Kernel": platform.release(),
        "Architecture": platform.machine(),
    }


# --- Commands that shell out -------------------------------------------

PACKAGE_PATTERNS = [
    "hifiberry-*",
    "hbos-*",
    "pipewire",
    "mpd",
    "librespot",
    "shairport-sync",
    "squeezelite",
    "raat",
]

SERVICE_PATTERNS = [
    "hifiberry*",
    "config-server*",
    "pipewire*",
    "mpd*",
    "librespot*",
    "shairport*",
    "squeezelite*",
    "raat*",
    "nqptp*",
    "sigmatcpserver*",
    "roomeq*",
    "aes67*",
    "usbaudio*",
    "sendspin*",
    "analoginput*",
    "acr-webmcp*",
    "nowplaying-sdl*",
    "sambamount*",
]


def _run(cmd: list, timeout: int = 10) -> str:
    """Run a command and return its stdout, or a note about why it failed.

    stdout wins whenever there is any -- that is the dpkg-query case, which
    routinely exits non-zero while still printing the matches it found. Only
    when a non-zero exit left stdout empty is stderr surfaced instead, so a
    permission error (e.g. journalctl run without the adm/systemd-journal
    group) shows up as a reason rather than a silent blank section.
    """
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"(command failed: {e})"
    stdout = result.stdout.strip()
    if stdout:
        return stdout
    if result.returncode != 0 and result.stderr.strip():
        return f"(command failed: {result.stderr.strip()})"
    return stdout


def collect_packages() -> str:
    """Installed versions of the HiFiBerry and player packages.

    dpkg-query exits non-zero for patterns that match nothing, which is normal
    here -- most systems have only a few players installed. check=False in
    _run keeps the matches we did get. A pattern can also match a package
    dpkg merely knows about (e.g. it was removed but not purged) rather than
    one that is installed; dpkg-query prints that as a line with an empty
    version field ("librespot "), which reads as broken output in a bug
    report, so those lines are dropped here.
    """
    raw = _run(
        ["dpkg-query", "-W", "-f=${Package} ${Version}\n"] + PACKAGE_PATTERNS
    )
    kept = []
    for line in raw.splitlines():
        parts = line.split(" ", 1)
        version = parts[1].strip() if len(parts) > 1 else ""
        if version:
            kept.append(line)
    return "\n".join(kept)


def collect_services() -> str:
    """State of the audio-related systemd units."""
    return _run(
        ["systemctl", "list-units", "--all", "--no-legend", "--no-pager"]
        + SERVICE_PATTERNS
    )


# journalctl's default output starts every line with a timestamp
# ("Aug 07 09:54:42"); with --no-hostname the hostname field that used to
# follow it is gone, so everything after the timestamp is "IDENTIFIER[PID]:
# MESSAGE". That tail is what two occurrences of the same error are
# compared on -- the timestamp itself must not be part of the key, or every
# occurrence of an otherwise identical message would count as distinct.
_JOURNAL_TIMESTAMP = re.compile(r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(.*)$")


def _dedup_journal(text: str, keep: int) -> str:
    """Collapse repeated journal messages into one entry each.

    A single restart-looping unit can otherwise fill the whole window with
    identical lines and crowd out every other error, which is exactly what a
    bug report needs to show. The text is walked once, in the chronological
    order journalctl prints it, keyed on everything after the timestamp; a
    repeat updates the existing entry's timestamp to the latest occurrence
    and bumps its count rather than appending a new line, so a unit that
    failed 190 times occupies one slot, not 190. At most `keep` distinct
    entries are kept: the most recently-first-seen ones, i.e. the last
    `keep` messages to appear for the first time in the input, still shown
    in that same chronological order.
    """
    if not text:
        return text

    order = []
    entries = {}
    for line in text.splitlines():
        match = _JOURNAL_TIMESTAMP.match(line)
        if match:
            timestamp, message = match.group(1), match.group(2)
        else:
            timestamp, message = None, line
        if message in entries:
            entry = entries[message]
            entry["count"] += 1
            if timestamp:
                entry["timestamp"] = timestamp
        else:
            entries[message] = {"timestamp": timestamp, "count": 1}
            order.append(message)

    kept = order[-keep:] if keep > 0 else []
    rendered = []
    for message in kept:
        entry = entries[message]
        prefix = f"{entry['timestamp']} " if entry["timestamp"] else ""
        suffix = f" (x{entry['count']})" if entry["count"] > 1 else ""
        rendered.append(f"{prefix}{message}{suffix}")
    return "\n".join(rendered)


def collect_journal(lines: int = 40) -> str:
    """The most recent distinct errors from the current boot.

    A flapping unit can produce dozens of identical lines in a row, so
    journalctl is asked for a much wider window than will be shown (ten
    times `lines`, with a floor of 200) and the result is collapsed down to
    at most `lines` distinct entries by _dedup_journal -- `lines` keeps its
    meaning from the caller's point of view, the number of entries shown.
    --no-hostname keeps the hostname (which regularly contains someone's
    real name) out of the report, the same reason Task 2 leaves Hostname out
    of the System section; the resulting "timestamp identifier: message"
    prefix shape is already handled by the PEM redaction walk.
    """
    fetch = max(lines * 10, 200)
    raw = _run(
        [
            "journalctl", "-b", "-p", "err", "--no-pager", "--no-hostname",
            "-n", str(fetch),
        ],
        timeout=20,
    )
    return _dedup_journal(raw, lines)


def collect_disk() -> str:
    """Free space on the root filesystem."""
    return _run(["df", "-h", "/"])


# --- Report assembly, redaction and CLI ---------------------------------


def build_report(journal_lines: int = 40) -> dict:
    """Collect every section of the diagnostic report."""
    return {
        "System": collect_system(),
        "OS": collect_os(),
        "Packages": collect_packages(),
        "Services": collect_services(),
        "Disk": collect_disk(),
        "Recent errors": collect_journal(lines=journal_lines),
    }


def redact_report(report: dict) -> dict:
    """Apply redaction to every string in the report, keeping its structure.

    JSON is redacted here rather than after serialisation: running the value
    patterns over rendered JSON would swallow the closing quote of a value like
    "password=hunter2" and produce invalid JSON.
    """
    redacted = {}
    for section, content in report.items():
        if isinstance(content, dict):
            redacted[section] = {
                k: redact_secrets(str(v)) for k, v in content.items()
            }
        else:
            redacted[section] = redact_secrets(str(content))
    return redacted


def render_text(report: dict) -> str:
    """Render the report as a plain text block, ready to paste into an issue."""
    parts = []
    for section, content in report.items():
        parts.append(f"## {section}")
        if isinstance(content, dict):
            if content:
                for name, value in content.items():
                    parts.append(f"{name}: {value}")
            else:
                parts.append("(none)")
        else:
            parts.append(str(content) if content else "(none)")
        parts.append("")
    return redact_secrets("\n".join(parts))


def setup_logging(verbose=False):
    """Configure logging for this command, mirroring systeminfo.setup_logging().

    Every failure that matters is already surfaced inside the report body as
    "(command failed: ...)", via the collectors' own return values -- so the
    WARNING/ERROR log lines the collectors (SystemInfo, hostname_utils, ...)
    emit along the way are redundant with what the user is about to paste
    into an issue, and would otherwise interleave with the report on a
    terminal. Unlike systeminfo, which defaults to WARNING, this command
    defaults above ERROR so that noise is suppressed by default; --verbose
    restores full logging for local debugging.
    """
    log_level = logging.DEBUG if verbose else logging.CRITICAL

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(log_level)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="config-supportinfo",
        description="Collect a redacted diagnostic report for HiFiBerryOS bug reports.",
    )
    parser.add_argument(
        "--json", action="store_true", help="output machine-readable JSON"
    )
    parser.add_argument(
        "--journal-lines",
        type=int,
        default=40,
        help="number of recent error lines to include (default: 40)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose logging"
    )
    args = parser.parse_args(argv)

    # Only main() configures logging: this module is also imported by
    # config-server and other tools, and setting the root logger's level at
    # import time would hijack their logging too.
    setup_logging(args.verbose)

    report = build_report(journal_lines=args.journal_lines)
    if args.json:
        print(json.dumps(redact_report(report), indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
