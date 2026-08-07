"""
config-supportinfo - collect a redacted diagnostic report for bug reports.

The output of this tool is meant to be pasted into public GitHub issues, so
everything it prints passes through redact_secrets() first.
"""

import argparse
import contextlib
import getpass
import json
import logging
import os
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

# HTTP "Authorization" headers that carry a credential. Bearer and Basic put
# a single opaque token after the scheme name (a JWT, or base64 of
# "user:pass" for Basic); Digest puts a comma-separated list of key="value"
# fields (username, response hash, ...) that are individually just as
# sensitive. Rather than parsing that structure, everything from the scheme
# name to the end of the line is treated as the credential and replaced as
# one unit -- simpler than the Digest fields, and still correct for the
# single-token schemes. Only these three scheme names are recognised: a
# scheme this does not know about (or a bare "Authorization:" with no
# scheme at all) is left untouched rather than guessed at, so the scheme
# name stays visible for whoever reads the report.
_AUTH_CREDENTIAL = re.compile(
    r"(?i)\b(Authorization\s*:\s*(?:Basic|Bearer|Digest)\s+)(\S.*)"
)

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
    "Authorization: <scheme> <credential>" headers for the Basic, Bearer and
    Digest schemes, and PEM private-key blocks
    (the body between a "-----BEGIN ... PRIVATE KEY-----" marker and its
    matching "-----END" marker -- or, if the block was truncated, e.g. by a
    log excerpt that cuts off mid-key, as far as the lines look like key
    material). PEM blocks are recognised no matter what precedes them on
    the line, so journalctl-prefixed and indented blocks are covered too;
    content that follows a truncated block is left untouched.
    """
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}:{REDACTED}@", text)
    text = _AUTH_CREDENTIAL.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
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
    "roomeq",
    "nowplaying-sdl",
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


# Marker _run() puts at the start of every failure string it returns,
# whatever the underlying reason. Used here to tell "the command ran and
# told us this unit doesn't exist" apart from "we don't know, the command
# didn't run" -- the two must not be treated the same when deciding what to
# suppress (see _merge_service_states).
_COMMAND_FAILED_PREFIX = "(command failed:"

# Explicit stand-in for a column with nothing to say (e.g. ACTIVE/SUB for a
# unit that only appeared in `list-unit-files`, never in `list-units`).
# Never blank: a blank cell collapses the column count for that row and
# breaks the alignment every other row relies on.
_NO_VALUE = "-"

# systemctl prefixes a unit-state glyph (a red "●" for a failed/not-found
# unit) directly onto the UNIT column of `list-units` output, glyph-then-space,
# ahead of the unit name -- unrelated to --no-legend, which only controls the
# header/footer. Left in place it becomes the first whitespace-split token,
# which shifts every following field over by one and corrupts the unit name
# used as this row's dict key. Stripped unconditionally before parsing; a
# normal line has nothing here to strip. The `\s*` allows for leading
# indentation ahead of the glyph itself -- real hardware puts the glyph at
# column 0, but nothing about the format guarantees that, and the
# unanchored version silently mis-parsed an indented glyph the same way
# the unstripped glyph itself once did.
_LEADING_GLYPH = re.compile(r"^\s*[^\w\s]+\s+")


def _parse_list_units(raw: str) -> dict:
    """Parse `systemctl list-units` output into {unit: (load, active, sub)}.

    Each line is "UNIT LOAD ACTIVE SUB DESCRIPTION"; DESCRIPTION may itself
    contain spaces (or be absent, e.g. for a "not-found" row), so only the
    first four fields are taken. A line with fewer than four fields is not
    a unit row -- it is skipped rather than raising, since a failed command
    is handled by the caller before this is ever called on its output.
    """
    states = {}
    for line in raw.splitlines():
        line = _LEADING_GLYPH.sub("", line, count=1)
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[:4]
        states[unit] = (load, active, sub)
    return states


def _parse_list_unit_files(raw: str) -> dict:
    """Parse `systemctl list-unit-files` output into {unit: enable_state}.

    Each line is "UNIT FILE STATE", optionally followed by a VENDOR PRESET
    column on newer systemd -- only the first two fields are read, so both
    shapes work.
    """
    states = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        unit, state = parts[0], parts[1]
        states[unit] = state
    return states


def _render_service_rows(rows: list) -> list:
    """Render (scope, unit, load, active, sub, enabled) tuples as an aligned table.

    Column widths are computed from exactly the rows being printed (post
    suppression) plus their headers, then every SCOPE/UNIT/LOAD/ACTIVE/SUB
    cell is left-padded to its column's width -- so the ENABLED column, and
    every column before it, starts at the same character offset on every
    row, header included. Padding is computed with plain str.ljust on the
    column values only; the "  " separator between columns is added on top
    of that, not folded into the width, so two adjacent equal-width columns
    are never visually ambiguous.

    SCOPE ("system" or "user") is its own leading column, not folded into
    UNIT, because "system" and "user" each define units with the same
    name (mpd.service exists, differently, in both) -- see
    collect_services for why the two scopes are never merged by name
    alone. Keeping scope as a column, rather than e.g. a "user/" prefix on
    the unit name, is what lets it line up and stay scannable alongside
    everything else.
    """
    headers = ("SCOPE", "UNIT", "LOAD", "ACTIVE", "SUB")
    widths = [
        max(len(headers[i]), max(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    def fixed_columns(values):
        return "  ".join(value.ljust(width) for value, width in zip(values, widths))

    lines = [fixed_columns(headers) + "  ENABLED"]
    for scope, unit, load, active, sub, enabled in rows:
        lines.append(
            fixed_columns((scope, unit, load, active, sub)) + f"  [enabled: {enabled}]"
        )
    return lines


def _service_rows_for_scope(scope: str, units_raw: str, files_raw: str) -> tuple:
    """Combine running state and enabled state into one row per unit, for one scope.

    `systemctl list-units` answers "is it running now"; `list-unit-files`
    answers "will it start on the next boot". A report that only carries
    the former is exactly the gap this exists to close -- "player works
    until I reboot, then it doesn't" is settled by the enabled state, not
    by whatever happens to be running at the moment someone runs
    config-supportinfo. The two are merged into one row per unit, not two
    separate sections, so a maintainer reading the report never has to
    cross-reference a unit name between them to answer both questions.

    Units that are neither installed nor enabled are dropped. SERVICE_PATTERNS
    matches every player this project supports, and most systems have only
    one or two of them installed in a given scope; a "not-found"/"not-found"
    row for each of the rest would bury the units that actually matter
    under noise nobody reads. This suppression only fires when *both*
    commands succeeded and *both* agree the unit is absent -- a command
    failure must never be read as "not installed", so a unit is kept (with
    "unknown" in place of whichever half failed) whenever either query
    could not run.

    A unit missing from `list-units` (it only appeared in list-unit-files,
    e.g. a static unit with no loaded instance) still gets a full-width
    ACTIVE/SUB placeholder rather than being collapsed to a single word --
    see _render_service_rows, which needs every row to carry the same
    number of columns to align them.

    Returns (rows, notes): rows are (scope, unit, load, active, sub,
    enabled) tuples, already scope-tagged so the caller can freely combine
    rows from multiple scopes into one table without their unit names
    colliding; notes are 0-2 "state unavailable" strings, one per command
    that failed, each naming this scope so a reader can tell system
    failures from user ones when both halves are shown together.
    """
    units_failed = units_raw.startswith(_COMMAND_FAILED_PREFIX)
    files_failed = files_raw.startswith(_COMMAND_FAILED_PREFIX)

    running = {} if units_failed else _parse_list_units(units_raw)
    enabled = {} if files_failed else _parse_list_unit_files(files_raw)

    rows = []
    for unit in sorted(set(running) | set(enabled)):
        load_active_sub = running.get(unit)
        if load_active_sub is None:
            load = "unknown" if units_failed else "not-found"
            load_active_sub = (load, _NO_VALUE, _NO_VALUE)
        load, active, sub = load_active_sub

        enable_state = enabled.get(unit)
        if enable_state is None:
            enable_state = "unknown" if files_failed else "not-found"

        if not units_failed and not files_failed:
            if load == "not-found" and enable_state == "not-found":
                continue

        rows.append((scope, unit, load, active, sub, enable_state))

    notes = []
    if units_failed:
        notes.append(f"({scope} running state unavailable: {units_raw})")
    if files_failed:
        notes.append(f"({scope} enabled state unavailable: {files_raw})")
    return rows, notes


# --- The player user's systemd --user instance --------------------------
#
# On HiFiBerryOS the player daemons (mpd, librespot, shairport, ...) run as
# systemd *user* services under a dedicated, unprivileged player account --
# not as system services. A Services section built only from `systemctl
# list-units` (the system manager) is therefore silent for exactly the
# reports that matter most: it shows config-server, sigmatcpserver,
# roomeq... and not one player, even when a player is installed, enabled
# and actively playing.


# Conservative: a valid Linux username, nothing else. Anything that does
# not match -- a comment, a blank line, an accidental sentence -- must
# fall through to the linger-directory fallback rather than being used
# verbatim as a --machine=<name>@.host target.
_PLAYER_USERNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _read_hifiberry_user_file() -> str:
    """Indirection so tests can replace the filesystem lookup.

    /etc/hifiberry.user is a single line holding the player username, when
    present. Root-owned, world-readable. Blank lines and "#"-prefixed
    comments are skipped; the first remaining line is used only if it
    looks like a real username (_PLAYER_USERNAME_RE) -- a comment-only or
    otherwise malformed file (e.g. just "# the player user") must not
    produce a bogus username, since that would build a broken --machine
    target and report the user scope unavailable instead of correctly
    falling through to the linger directory.
    """
    with open("/etc/hifiberry.user") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line if _PLAYER_USERNAME_RE.match(line) else ""
    return ""


def _list_linger_users() -> list:
    """Indirection so tests can replace the filesystem lookup.

    systemd creates one file per lingering user under this directory, named
    after the username; a lingering user's systemd --user instance keeps
    running without an active login session, which is required for the
    player's units to survive a reboot without anyone signing in.
    """
    return sorted(os.listdir("/var/lib/systemd/linger/"))


def _detect_player_user() -> tuple:
    """Find the username the player daemons' systemd --user instance runs as.

    /etc/hifiberry.user is the primary source and wins unconditionally when
    it resolves to a valid name -- the linger fallback below is never even
    consulted in that case. Older images may not carry the file (or it may
    be empty/comment-only/malformed, see _read_hifiberry_user_file), so the
    fallback is whoever has systemd linger enabled: the player user must
    have it (its user services could not otherwise survive a reboot
    without an interactive login), and on a HiFiBerryOS install it is
    normally the only lingering user. If neither source resolves to
    exactly one name, no username is guessed -- the caller reports the
    user scope as unavailable, with the reason returned here, rather than
    silently querying the wrong account or none at all.

    Returns (username, source) on success -- source names *how* the user
    was found (e.g. "from /etc/hifiberry.user"), not the username itself,
    so a maintainer can audit the detection in a public bug report without
    the report ever containing what is, on every device seen so far, a
    person's real login name. Returns (None, reason) on failure, reason
    being a human-readable explanation.
    """
    try:
        name = _read_hifiberry_user_file()
    except OSError:
        name = ""
    if name:
        return name, "from /etc/hifiberry.user"

    try:
        entries = [u for u in _list_linger_users() if not u.startswith(".")]
    except OSError:
        entries = []

    if len(entries) == 1:
        return entries[0], "from linger (single account)"
    if not entries:
        return None, (
            "no player user found (/etc/hifiberry.user missing and no "
            "lingering user in /var/lib/systemd/linger/)"
        )
    return None, (
        f"ambiguous player user: {len(entries)} lingering users found, "
        "none chosen"
    )


def _current_user() -> str:
    """Indirection so tests can replace the process-identity lookup."""
    try:
        return getpass.getuser()
    except OSError:
        return ""


def _scrub_username(text: str, player_user: str) -> str:
    """Strip the player username back out of raw systemctl output.

    `--machine=<player_user>@.host` is passed on the command line, and a
    connection failure (unreachable machine, no such user, ...) routinely
    echoes it straight back in stderr -- which _run() then folds into a
    "(command failed: ...)" note. That note reaches the rendered report
    unredacted (redact_secrets targets credentials, not usernames), so
    without this the same real login name _detect_player_user's source
    string was deliberately built to avoid printing could still leak
    through a failure message. Applied to both list-units and
    list-unit-files output for the user scope, successful or not; a
    literal username never legitimately appears in either.
    """
    if not player_user:
        return text
    return text.replace(f"{player_user}@.host", "<player>@.host").replace(
        player_user, "<player>"
    )


def _collect_user_service_rows() -> tuple:
    """Player-daemon units, queried from the player user's systemd --user instance.

    `systemctl --user` talks to the calling process's own session bus, so
    it only reaches the right instance for free when config-supportinfo
    happens to run as the player user itself. Every other case --
    config-supportinfo run as root, or as any other account, which is the
    common case for a diagnostic tool -- needs `--machine=<user>@.host` to
    reach that user's instance instead of failing or silently querying the
    wrong (or no) session.

    If the player user cannot be identified at all, this returns no rows
    and one explanatory note rather than raising: a report with an
    "unavailable" line and an otherwise complete system-scope section is
    far more useful than one that aborts before it can print anything.

    A successful detection is also noted, naming *how* the user was found
    (_detect_player_user's source string) rather than the username itself
    -- so a maintainer can tell a file-based detection from a linger guess
    and spot a wrong one, without the report ever containing what is, on
    every device seen so far, a person's real login name. The same note
    also records *which* of the two access paths above was taken (direct
    session bus vs. --machine): the collection functions are shared between
    the CLI and the config-server endpoint, but which path runs is decided
    by the calling process's own identity, which is not shared -- the CLI
    usually runs as the player user itself, config-server always runs as
    root. The two paths can behave differently (--machine depends on
    machined and a reachable linger session), so a reader comparing a bug
    report against what the CLI shows locally needs to know which path
    produced the rows in front of them.
    """
    player_user, source = _detect_player_user()
    if player_user is None:
        return [], [f"(user services unavailable: {source})"]

    machine = (
        [] if _current_user() == player_user
        else [f"--machine={player_user}@.host"]
    )
    access = "direct session bus" if not machine else "via --machine"
    notes = [f"(user scope: {source}; access: {access})"]

    units_raw = _scrub_username(
        _run(
            ["systemctl", "--user"] + machine
            + ["list-units", "--all", "--no-legend", "--no-pager"]
            + SERVICE_PATTERNS
        ),
        player_user,
    )
    files_raw = _scrub_username(
        _run(
            ["systemctl", "--user"] + machine
            + ["list-unit-files", "--no-legend", "--no-pager"]
            + SERVICE_PATTERNS
        ),
        player_user,
    )
    rows, scope_notes = _service_rows_for_scope("user", units_raw, files_raw)
    return rows, notes + scope_notes


def collect_services() -> str:
    """Running and enabled state of the audio-related systemd units.

    Covers both scopes that matter on HiFiBerryOS: the system scope
    (infrastructure daemons like config-server and sigmatcpserver) and the
    user scope the player daemons actually run in (see the module note
    above _read_hifiberry_user_file). The two are collected, suppressed
    (_service_rows_for_scope) and queried independently, then combined
    into one table with an explicit SCOPE column (_render_service_rows) --
    never merged by unit name alone, since "system" and "user" each define
    units of the same name (mpd.service exists, differently, in both), and
    a same-name merge could show a player as not-found while its real,
    running user unit sits right next to it.

    Each half's two systemctl calls go through _run independently, so a
    failure anywhere -- system or user, running-state or enabled-state,
    missing systemctl, unreachable player user -- is reported as its own
    note and never blanks out the rest of the section.
    """
    system_units = _run(
        ["systemctl", "list-units", "--all", "--no-legend", "--no-pager"]
        + SERVICE_PATTERNS
    )
    system_files = _run(
        ["systemctl", "list-unit-files", "--no-legend", "--no-pager"]
        + SERVICE_PATTERNS
    )
    system_rows, system_notes = _service_rows_for_scope("system", system_units, system_files)
    user_rows, user_notes = _collect_user_service_rows()

    rows = system_rows + user_rows
    lines = system_notes + user_notes
    if rows:
        lines.extend(_render_service_rows(rows))
    return "\n".join(lines)


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

    The occurrence count is rendered as a "(xN)" marker at the *start* of
    the line, not the end. redact_secrets()'s Authorization-header pattern
    is deliberately greedy -- a credential can contain almost any character,
    so it replaces everything from the auth scheme to end of line -- and a
    trailing "(xN)" on a redacted line would fall inside that span and
    vanish, silently turning "this failed 37 times" back into "this failed"
    for exactly the lines where the repeat count matters most. A leading
    marker sits before anything redaction ever touches, so it survives
    structurally instead of needing redaction to special-case this format.
    Markers are right-aligned to a common width and lines with no repeat
    are left-padded by that same width, so every timestamp still starts in
    the same column and the section stays scannable.
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
    markers = {
        message: f"(x{entries[message]['count']})"
        for message in kept
        if entries[message]["count"] > 1
    }
    width = max((len(marker) for marker in markers.values()), default=0)

    rendered = []
    for message in kept:
        entry = entries[message]
        line = ""
        if width:
            line += markers.get(message, "").rjust(width) + " "
        if entry["timestamp"]:
            line += f"{entry['timestamp']} "
        line += message
        rendered.append(line)
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


@contextlib.contextmanager
def quiet_collectors():
    """Silence the collectors' WARNING/ERROR logging for the duration of a call.

    setup_logging() is the CLI's answer to the same noise (see its
    docstring), but it is not safe for a long-lived process to call: it
    tears down and replaces every handler on the root logger, which for
    config-supportinfo's one-shot process is fine and for config-server --
    whose other routes must keep logging exactly as they already do --
    would be a permanent, global side effect of one route. This only raises
    the root logger's *level* for the lifetime of the with-block and always
    restores the previous level on the way out, success or exception, so it
    can wrap a single request's collection without touching config-server's
    own handlers or leaking the change into the requests that follow.
    """
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        root_logger.setLevel(previous_level)


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
