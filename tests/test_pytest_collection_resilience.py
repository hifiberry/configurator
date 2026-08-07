# tests/test_pytest_collection_resilience.py
"""Guards against a specific regression: tests/test_server_supportinfo.py
imports flask, a declared-but-not-guaranteed-installed dependency, and a
bare `import flask` failure during collection does not just skip that one
file -- pytest aborts collection entirely ("Interrupted: N errors during
collection"), which silently skips every other test in the suite too.
There is no CI to catch that, so the normal `python3 -m pytest tests/`
command must keep working whether or not flask happens to be installed.

Each test here runs pytest in a *subprocess* with flask hidden from
sys.modules (rather than uninstalling it, which would affect the rest of
this run) -- see _run_with_flask_hidden -- so the parent test run's own
already-imported flask (if any) is unaffected.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Runs pytest.main() in a fresh interpreter with sys.modules['flask'] set to
# None first. That makes any subsequent `import flask` raise ImportError --
# the same failure mode as flask simply not being installed -- without
# actually uninstalling anything from the environment this test itself runs
# in.
_HIDE_FLASK_AND_RUN_PYTEST = (
    "import sys; sys.modules['flask'] = None; "
    "import pytest; sys.exit(pytest.main(sys.argv[1:]))"
)


def _run_with_flask_hidden(*pytest_args):
    return subprocess.run(
        [sys.executable, "-c", _HIDE_FLASK_AND_RUN_PYTEST, *pytest_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_flask_dependent_file_is_skipped_not_a_collection_error():
    """With flask hidden, the flask-dependent test module is skipped
    (pytest.importorskip), not a collection error -- that is what keeps a
    missing flask from taking the rest of the suite down with it."""
    result = _run_with_flask_hidden("tests/test_server_supportinfo.py", "-q")
    output = result.stdout + result.stderr
    assert "Interrupted" not in output
    assert "error" not in output.lower()
    assert "1 skipped" in output
    # Exit code 5 ("no tests ran") is expected here, not a failure: the
    # module's only outcome is the import-time skip, so pytest collected
    # zero runnable items from it. What this test guards against is exit
    # code 2 (Interrupted) or a nonzero-because-of-an-error outcome from
    # collection blowing up instead of degrading to a clean skip.
    assert result.returncode in (0, 5)


def test_full_suite_still_runs_and_reports_its_real_count_without_flask():
    """The regression this guards against: `python3 -m pytest tests/`
    aborting collection entirely and reporting nothing wrong. With flask
    hidden, the rest of the suite (everything except the flask-dependent
    modules) must still collect and run, and pytest's own exit code must
    reflect that (0 -- skips are not failures).

    Excludes this file itself: it spawns pytest subprocesses, so including
    it in a subprocess's own "tests/" target would recursively spawn more
    subprocesses doing the same thing.
    """
    result = _run_with_flask_hidden(
        "tests/", "-q", "--ignore=tests/test_pytest_collection_resilience.py"
    )
    output = result.stdout + result.stderr
    assert "Interrupted" not in output
    assert "during collection" not in output
    assert result.returncode == 0
    # Comfortably more than the handful of files that could plausibly
    # depend on flask -- proves the bulk of the suite actually ran rather
    # than being silently swallowed by the collection abort this guards
    # against.
    assert " passed" in output
    passed = int(output.split(" passed")[0].strip().split()[-1])
    assert passed > 300


def test_server_supportinfo_tests_execute_when_flask_is_present():
    """The other direction: when flask *is* importable, the server tests
    must not be silently skipped -- they need to actually run and pass."""
    pytest.importorskip("flask", reason="only meaningful when flask is installed")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_server_supportinfo.py", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert "skipped" not in output
    assert "passed" in output
    assert result.returncode == 0
