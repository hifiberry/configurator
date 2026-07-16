import pytest

from configurator.extensions.jobs import (
    ExtensionBusy,
    JobRegistry,
    PHASE_DONE,
    PHASE_DOWNLOADING,
    PHASE_FAILED,
    PHASE_QUEUED,
)


def _registry(**kwargs):
    counter = {"n": 0}

    def ids():
        counter["n"] += 1
        return f"job-{counter['n']}"

    kwargs.setdefault("id_factory", ids)
    kwargs.setdefault("clock", lambda: 1000.0)
    return JobRegistry(**kwargs)


def test_new_job_starts_queued():
    job = _registry().create("hifiberry-tidal-connect", "install")
    assert job.phase == PHASE_QUEUED
    assert job.percent == 0
    assert job.id == "job-1"


def test_get_returns_the_job():
    registry = _registry()
    job = registry.create("hifiberry-tidal-connect", "install")
    assert registry.get(job.id) is job


def test_get_unknown_id_returns_none():
    assert _registry().get("nope") is None


def test_set_phase_updates_phase_and_percent():
    job = _registry().create("x", "install")
    job.set_phase(PHASE_DOWNLOADING, 42.0)
    assert job.phase == PHASE_DOWNLOADING
    assert job.percent == 42.0


def test_set_phase_without_percent_keeps_previous():
    job = _registry().create("x", "install")
    job.set_phase(PHASE_DOWNLOADING, 42.0)
    job.set_phase(PHASE_DOWNLOADING)
    assert job.percent == 42.0


def test_log_is_capped_to_a_ring_buffer():
    job = _registry(max_log_lines=3).create("x", "install")
    for i in range(10):
        job.append_log(f"line {i}")
    assert job.to_dict()["log"] == ["line 7", "line 8", "line 9"]


def test_finish_marks_done_and_stamps_finished_at():
    job = _registry().create("x", "install")
    job.finish(PHASE_DONE)
    assert job.phase == PHASE_DONE
    assert job.percent == 100
    assert job.to_dict()["finished_at"] == 1000.0


def test_finish_failed_records_exit_code_and_error():
    job = _registry().create("x", "install")
    job.finish(PHASE_FAILED, exit_code=100, error="dpkg was unhappy")
    data = job.to_dict()
    assert data["phase"] == PHASE_FAILED
    assert data["exit_code"] == 100
    assert data["error"] == "dpkg was unhappy"


def test_second_job_while_one_is_active_raises_busy():
    registry = _registry()
    registry.create("a", "install")
    with pytest.raises(ExtensionBusy):
        registry.create("b", "install")


def test_new_job_allowed_once_the_previous_finished():
    registry = _registry()
    first = registry.create("a", "install")
    first.finish(PHASE_DONE)
    assert registry.create("b", "install").id == "job-2"


def test_active_job_is_none_once_finished():
    registry = _registry()
    job = registry.create("a", "install")
    assert registry.active_job is job
    job.finish(PHASE_DONE)
    assert registry.active_job is None


def test_to_dict_is_json_shaped():
    data = _registry().create("hifiberry-tidal-connect", "install").to_dict()
    assert data["id"] == "job-1"
    assert data["package"] == "hifiberry-tidal-connect"
    assert data["action"] == "install"
    assert data["started_at"] == 1000.0
    assert data["log"] == []
