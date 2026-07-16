#!/usr/bin/env python3
"""Extension catalog: read apt metadata and apply the marker gate."""

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Extension metadata is written in debian/control with an XB- prefix (dpkg's
# mechanism for custom binary-package fields). dpkg-gencontrol STRIPS that
# prefix, so a properly built deb's repo record has "Hifiberry-Extension", while
# a hand-crafted deb (dpkg-deb --build) or the raw control keeps the "Xb-"
# prefix. record_field() accepts both, so these constants use the stripped form.
MARKER_FIELD = "Hifiberry-Extension"
NAME_FIELD = "Extension-Name"
CATEGORY_FIELD = "Extension-Category"
REBOOT_FIELD = "Extension-Needs-Reboot"
ICON_URL_FIELD = "Extension-Icon-Url"

VALID_CATEGORIES = ("player", "dsp", "tool")
DEFAULT_CATEGORY = "tool"

VALID_NEEDS_REBOOT = ("no", "maybe", "yes")
DEFAULT_NEEDS_REBOOT = "no"

# Debian policy allows more, but this is deliberately strict: it is the
# first line of defence before any package name reaches apt.
VALID_PACKAGE_RE = re.compile(r'^[a-z0-9][a-z0-9+.-]*$')


@dataclass
class PackageInfo:
    """One package as seen in the apt cache. The only apt-shaped input."""
    name: str
    record: Dict[str, str] = field(default_factory=dict)
    candidate_version: Optional[str] = None
    installed_version: Optional[str] = None


@dataclass
class Extension:
    package: str
    name: str
    category: str
    summary: str
    description: str
    version: Optional[str]
    installed_version: Optional[str]
    state: str
    needs_reboot: str
    icon_url: Optional[str] = None
    # Where this extension comes from: "apt" for an apt-repo package, or
    # "github:owner/name" for a GitHub-release package. download_url/sha256 are
    # server-side install hints for the GitHub path and are not serialized.
    source: str = "apt"
    download_url: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "package": self.package,
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "description": self.description,
            "version": self.version,
            "installed_version": self.installed_version,
            "state": self.state,
            "needs_reboot": self.needs_reboot,
            "icon_url": self.icon_url,
            "source": self.source,
        }


def record_field(record: Dict[str, str], name: str, default: str = "") -> str:
    """Look up an extension control field, tolerant of casing and the XB- prefix.

    Two things vary in how the field reaches us:

    * **Casing** — dpkg normalizes field names in the repo ``Packages`` index
      (``Xb-Hifiberry-Extension``). python3-apt's ``Record`` is case-insensitive,
      but ``dict(record)`` (used by apt_package_source to make a plain,
      serializable, testable dict) freezes that casing.
    * **The XB- prefix** — authors write ``XB-Hifiberry-Extension`` in
      debian/control. ``dpkg-buildpackage`` strips the prefix to
      ``Hifiberry-Extension``; ``dpkg-deb --build`` and the raw control keep it.

    So try the bare name and the ``XB-`` prefixed name, each case-insensitively.
    """
    for candidate in (name, "XB-" + name):
        if candidate in record:
            return record[candidate]
        target = candidate.lower()
        for key, value in record.items():
            if key.lower() == target:
                return value
    return default


def is_extension_record(record: Dict[str, str]) -> bool:
    """True only for a record explicitly marked as a HiFiBerry extension.

    This is the security boundary: everything installable passes through here.
    """
    return str(record_field(record, MARKER_FIELD)).strip().lower() == "yes"


def _split_description(raw: str):
    """Debian Description: first line is the summary, the rest is the body."""
    if not raw:
        return "", ""
    lines = raw.split("\n")
    summary = lines[0].strip()
    body_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        # A lone "." is Debian's blank-line marker.
        body_lines.append("" if stripped == "." else stripped)
    return summary, "\n".join(body_lines).strip()


def _state(candidate_version, installed_version) -> str:
    if installed_version is None:
        return "available"
    if candidate_version and candidate_version != installed_version:
        return "upgradable"
    return "installed"


def build_extension(info: PackageInfo) -> Optional[Extension]:
    """Build an Extension, or None if the package is not marked as one."""
    if not is_extension_record(info.record):
        return None

    category = str(record_field(info.record, CATEGORY_FIELD)).strip().lower()
    if category not in VALID_CATEGORIES:
        category = DEFAULT_CATEGORY

    needs_reboot = str(record_field(info.record, REBOOT_FIELD)).strip().lower()
    if needs_reboot not in VALID_NEEDS_REBOOT:
        needs_reboot = DEFAULT_NEEDS_REBOOT

    summary, description = _split_description(record_field(info.record, "Description"))

    return Extension(
        package=info.name,
        name=str(record_field(info.record, NAME_FIELD)).strip() or info.name,
        category=category,
        summary=summary,
        description=description,
        version=info.candidate_version,
        installed_version=info.installed_version,
        state=_state(info.candidate_version, info.installed_version),
        needs_reboot=needs_reboot,
        icon_url=str(record_field(info.record, ICON_URL_FIELD)).strip() or None,
    )


def apt_package_source() -> List[PackageInfo]:
    """Read the real apt cache. Imported lazily: python3-apt is absent in the
    deb build chroot and in unit tests."""
    import apt

    cache = apt.Cache()
    packages = []
    for pkg in cache:
        candidate = pkg.candidate
        if candidate is None:
            continue
        try:
            # Cheap pre-filter before converting the whole cache to dicts: apt's
            # Record.get is case-insensitive, and we accept both the stripped and
            # XB- prefixed marker names (see record_field).
            raw = candidate.record
            marker = raw.get(MARKER_FIELD) or raw.get("XB-" + MARKER_FIELD)
            if str(marker or "").strip().lower() != "yes":
                continue
            record = dict(raw)
        except Exception as e:  # a malformed record must not kill the catalog
            logger.debug(f"Skipping {pkg.name}: unreadable record: {e}")
            continue
        packages.append(PackageInfo(
            name=pkg.name,
            record=record,
            candidate_version=candidate.version,
            installed_version=pkg.installed.version if pkg.installed else None,
        ))
    return packages


class ExtensionCatalog:
    """The catalog is the apt repo. Nothing else is a source of truth."""

    def __init__(self, package_source: Optional[Callable[[], List[PackageInfo]]] = None):
        self._package_source = package_source or apt_package_source

    def list_extensions(self) -> List[Extension]:
        extensions = []
        for info in self._package_source():
            ext = build_extension(info)
            if ext is not None:
                extensions.append(ext)
        extensions.sort(key=lambda e: e.name.lower())
        return extensions

    def get_extension(self, package: str) -> Optional[Extension]:
        """Return the extension, or None if unknown OR not marked.

        Callers rely on None meaning 'refuse to install'.
        """
        if not VALID_PACKAGE_RE.match(package or ""):
            return None
        for info in self._package_source():
            if info.name == package:
                return build_extension(info)
        return None
