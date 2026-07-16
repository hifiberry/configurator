from unittest.mock import MagicMock

import pytest

from configurator.booteeprom import (
    EepromConfigError,
    needs_psu_workaround,
    set_psu_max_current,
)


def _runner(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = ""
    return MagicMock(return_value=r)


def _capturing_runner(read_stdout="", read_returncode=0, apply_returncode=0):
    """Runner that captures the path passed to --apply and, before this
    function returns, records the *content* of that file -- so tests can
    assert on what was actually about to be written to the EEPROM even
    though the implementation cleans the temp file up afterwards."""
    calls = []
    captured = {}

    def run(args, **kwargs):
        calls.append(args)
        r = MagicMock()
        r.stderr = ""
        if "--apply" in args:
            path = args[-1]
            with open(path) as f:
                captured["content"] = f.read()
            captured["path"] = path
            r.returncode = apply_returncode
            r.stdout = ""
        else:
            r.returncode = read_returncode
            r.stdout = read_stdout
        return r

    runner = MagicMock(side_effect=run)
    return runner, calls, captured


# Ground truth, captured from a real CM5 via `rpi-eeprom-config`.
GROUND_TRUTH_CONFIG = (
    "[all]\n"
    "BOOT_UART=1\n"
    "# Default BOOT_ORDER for provisioning\n"
    "# SD -> NVMe -> USB -> Network\n"
    "BOOT_ORDER=0xf2461\n"
)


def test_pi5_and_cm5_need_the_workaround():
    assert needs_psu_workaround("5") is True
    assert needs_psu_workaround("CM5") is True


def test_older_models_do_not():
    assert needs_psu_workaround("4") is False
    assert needs_psu_workaround("CM4") is False
    assert needs_psu_workaround("3B") is False


def test_sets_value_when_absent():
    run = _runner(stdout="[all]\nBOOT_UART=1\n")
    assert set_psu_max_current(3000, runner=run) is True
    applied = run.call_args_list[-1].args[0]
    assert "--apply" in applied


def test_no_change_when_already_set():
    run = _runner(stdout="[all]\nBOOT_UART=1\nPSU_MAX_CURRENT=3000\n")
    assert set_psu_max_current(3000, runner=run) is False
    # only the read call should have happened
    assert run.call_count == 1


def test_existing_different_value_is_replaced():
    run = _runner(stdout="[all]\nPSU_MAX_CURRENT=5000\n")
    assert set_psu_max_current(3000, runner=run) is True


def test_workaround_versions_match_the_gadget_capability_table():
    """Every model needing the PSU workaround must itself support gadget mode."""
    from configurator.pimodel import USB_GADGET_SUPPORT
    from configurator.booteeprom import PSU_WORKAROUND_VERSIONS

    for version in PSU_WORKAROUND_VERSIONS:
        assert USB_GADGET_SUPPORT.get(version) is not None


# --- Finding 4: inspect actual content written, using the ground-truth config ---


def test_existing_keys_survive_including_boot_order():
    runner, calls, captured = _capturing_runner(read_stdout=GROUND_TRUTH_CONFIG)
    assert set_psu_max_current(3000, runner=runner) is True

    content = captured["content"]
    assert "BOOT_UART=1" in content
    assert "BOOT_ORDER=0xf2461" in content
    assert "[all]" in content


def test_new_key_present_exactly_once():
    runner, calls, captured = _capturing_runner(read_stdout=GROUND_TRUTH_CONFIG)
    assert set_psu_max_current(3000, runner=runner) is True

    content = captured["content"]
    assert content.count("PSU_MAX_CURRENT=") == 1
    assert "PSU_MAX_CURRENT=3000" in content


def test_replacing_existing_value_does_not_duplicate_and_preserves_boot_order():
    existing = GROUND_TRUTH_CONFIG + "PSU_MAX_CURRENT=5000\n"
    runner, calls, captured = _capturing_runner(read_stdout=existing)
    assert set_psu_max_current(3000, runner=runner) is True

    content = captured["content"]
    assert content.count("PSU_MAX_CURRENT=") == 1
    assert "PSU_MAX_CURRENT=3000" in content
    assert "PSU_MAX_CURRENT=5000" not in content
    assert "BOOT_ORDER=0xf2461" in content


# --- Finding 1: a failed/untrustworthy read must never be applied ---


def test_failed_read_raises_and_never_applies():
    """A nonzero returncode from the read must be a hard failure -- never
    derive a config from it, and never touch --apply. This reproduces the
    real data-loss bug: previously a failed read (stdout='') was silently
    treated as 'no existing keys' and a config containing ONLY
    PSU_MAX_CURRENT was applied, wiping BOOT_ORDER/BOOT_UART."""
    run = _runner(stdout="", returncode=1)
    with pytest.raises(EepromConfigError):
        set_psu_max_current(3000, runner=run)
    apply_calls = [c for c in run.call_args_list if "--apply" in c.args[0]]
    assert apply_calls == []


def test_empty_read_output_raises_and_never_applies():
    run = _runner(stdout="", returncode=0)
    with pytest.raises(EepromConfigError):
        set_psu_max_current(3000, runner=run)
    apply_calls = [c for c in run.call_args_list if "--apply" in c.args[0]]
    assert apply_calls == []


def test_garbage_read_output_raises_and_never_applies():
    run = _runner(stdout="this is not a valid eeprom config at all\n", returncode=0)
    with pytest.raises(EepromConfigError):
        set_psu_max_current(3000, runner=run)
    apply_calls = [c for c in run.call_args_list if "--apply" in c.args[0]]
    assert apply_calls == []


def test_failed_apply_raises_rather_than_reporting_success():
    runner, calls, captured = _capturing_runner(
        read_stdout=GROUND_TRUTH_CONFIG, apply_returncode=1
    )
    with pytest.raises(EepromConfigError):
        set_psu_max_current(3000, runner=runner)
    # the apply call did happen, but it failed, and that must surface as an
    # exception rather than a truthy "success" return value.
    assert "content" in captured
