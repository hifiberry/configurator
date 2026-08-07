# tests/test_auth_policy_supportinfo.py
import fnmatch
import json
import os

import pytest

POLICY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "auth", "config.json",
)

# The endpoint under guard, in its two live representations:
#  - SUPPORTINFO_REMAINDER: what an ok-rule "paths" pattern is actually
#    matched against today, once this manifest's own match_prefix
#    ("/api/config/v1") has been stripped from the request URI by
#    hifiberry_auth.manifests.TierMap._manifest_for.
#  - SUPPORTINFO_ROUTE: the raw Flask route registered in
#    configurator/server.py (`/api/v1/supportinfo`). A pattern equal to
#    this string is inert under today's match_prefix, but it unambiguously
#    names the intent "let this endpoint through", and would go live the
#    moment match_prefix or the service topology changes. Checked too, so
#    that class of mistake doesn't sit dormant in the policy waiting for a
#    future refactor to activate it.
SUPPORTINFO_REMAINDER = "/supportinfo"
SUPPORTINFO_ROUTE = "/api/v1/supportinfo"


def _policy():
    with open(POLICY) as f:
        return json.load(f)


# Mirrors hifiberry_auth.manifests._path_matches
# (packages/hifiberry-auth/hifiberry-auth/src/hifiberry_auth/manifests.py)
# exactly: split pattern and path on "/", compare segment by segment with
# fnmatch.fnmatchcase, and treat a "**" segment as "matches the rest,
# including nothing" (manifests.py requires it be last; this mirror does
# too, since it returns as soon as it sees one). configurator cannot import
# hifiberry-auth -- different package, not a dependency, and adding one is
# out of scope -- so this is a small, explicit reimplementation rather than
# an approximation. A prefix/substring check (what this file used to do)
# is *not* equivalent: it misses globs like "/support*" or "/**" that the
# real matcher would honor, which is how this gap got past review once
# already. If manifests.py's matching semantics change, this comment is the
# pointer to come re-check them.
def _segments(path):
    path = path.split("?", 1)[0].split("#", 1)[0]
    return [s for s in path.strip("/").split("/") if s != ""]


def _path_matches(pattern, path):
    pat = _segments(pattern)
    seg = _segments(path)
    for i, p in enumerate(pat):
        if p == "**":          # matches the rest, including nothing (must be last)
            return True
        if i >= len(seg) or not fnmatch.fnmatchcase(seg[i], p):
            return False
    return len(pat) == len(seg)


def _ok_paths():
    return [
        path
        for rule in _policy()["rules"]
        if rule.get("tier") == "ok"
        for path in rule.get("paths", [])
    ]


def test_default_tier_is_risky():
    assert _policy()["default_tier"] == "risky"


def test_supportinfo_is_not_in_any_ok_rule():
    """The support report exposes journal errors, mount paths and the full
    package inventory — far more than /systeminfo, which is deliberately ok.
    An ok-rule pattern that the gateway's matcher would actually match
    against /supportinfo -- whether written as a literal path, a glob like
    /support* or /**, or the raw internal route -- would publish all of
    that to anyone on the network. If this test fails, that is what has
    happened.
    """
    for pattern in _ok_paths():
        for candidate in (SUPPORTINFO_REMAINDER, SUPPORTINFO_ROUTE):
            assert not _path_matches(pattern, candidate), (
                f"/supportinfo must stay authenticated, but ok pattern "
                f"{pattern!r} matches {candidate!r}"
            )


def test_systeminfo_is_still_ok_so_the_test_above_is_meaningful():
    assert "/systeminfo" in _ok_paths()


# --- Guard the matcher itself: prove it recognizes the shapes that slipped
# past the old prefix-only check, and that it doesn't fire on unrelated
# entries (so it can't rot into "always fails"). These exercise
# _path_matches() directly rather than mutating the real policy file, which
# stays untouched by this test suite; the equivalent mutation was also run
# by hand against the live auth/config.json (see task-12-report.md) to
# confirm the guard above genuinely fails when one of these patterns is
# actually added.
@pytest.mark.parametrize("pattern", ["/support*", "/**", "/api/v1/supportinfo", "/supportinfo"])
def test_matcher_recognizes_patterns_that_would_expose_supportinfo(pattern):
    assert _path_matches(pattern, SUPPORTINFO_REMAINDER) or _path_matches(pattern, SUPPORTINFO_ROUTE), (
        f"expected {pattern!r} to match one of the live supportinfo paths"
    )


def test_matcher_does_not_fire_on_an_unrelated_ok_pattern():
    assert not _path_matches("/systeminfo", SUPPORTINFO_REMAINDER)
    assert not _path_matches("/systeminfo", SUPPORTINFO_ROUTE)
