# tests/test_auth_policy_supportinfo.py
import json
import os

POLICY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "auth", "config.json",
)


def _policy():
    with open(POLICY) as f:
        return json.load(f)


def test_default_tier_is_risky():
    assert _policy()["default_tier"] == "risky"


def test_supportinfo_is_not_in_any_ok_rule():
    """The support report exposes journal errors, mount paths and the full
    package inventory — far more than /systeminfo, which is deliberately ok.
    Adding /supportinfo to an ok rule would publish all of that to anyone on
    the network. If this test fails, that is what has happened.
    """
    for rule in _policy()["rules"]:
        if rule.get("tier") != "ok":
            continue
        for path in rule.get("paths", []):
            assert not path.startswith("/supportinfo"), (
                f"/supportinfo must stay authenticated, found in ok rule: {path}"
            )


def test_systeminfo_is_still_ok_so_the_test_above_is_meaningful():
    ok_paths = [p for r in _policy()["rules"] if r.get("tier") == "ok" for p in r.get("paths", [])]
    assert "/systeminfo" in ok_paths
