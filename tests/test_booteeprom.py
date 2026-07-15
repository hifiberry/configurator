from unittest.mock import MagicMock

from configurator.booteeprom import needs_psu_workaround, set_psu_max_current


def _runner(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    return MagicMock(return_value=r)


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
