# tests/test_supportinfo_quiet_collectors_concurrency.py
"""quiet_collectors() is used by a route served by config-server under
waitress (threads=6 in server.py), so more than one call can be in flight
at once -- either two /supportinfo requests overlapping, or a /supportinfo
request overlapping any other route. Both scenarios here run without flask
or the Flask test client: they exercise supportinfo.quiet_collectors()
directly, since it is the shared primitive both the CLI (never concurrent)
and the endpoint (always potentially concurrent) sit on top of.
"""
import logging
import threading

from configurator import supportinfo

_TIMEOUT = 5


def test_overlapping_calls_do_not_leave_logging_stuck():
    """A level-based, save/restore implementation of quiet_collectors() is
    racy under this exact interleaving:

        A enters  (saves the true original level, raises it)
        B enters  (saves the *already-raised* level as "its" original)
        A exits   (restores the true original -- correct, but momentary)
        B exits   (restores "its" original, i.e. the raised level again)

    B's restore re-raises the level right after A correctly lowered it,
    and nothing ever lowers it again -- config-server's logging is silenced
    for the rest of the process's life, with no error. The four threading
    Events below force exactly that ordering deterministically, rather
    than hoping timing happens to line it up.
    """
    root_logger = logging.getLogger()
    original_level = root_logger.level

    a_inside = threading.Event()
    b_inside = threading.Event()
    a_exited = threading.Event()
    b_may_exit = threading.Event()

    def thread_a():
        with supportinfo.quiet_collectors():
            a_inside.set()
            assert b_inside.wait(_TIMEOUT), "thread b never entered"
        a_exited.set()

    def thread_b():
        assert a_inside.wait(_TIMEOUT), "thread a never entered"
        with supportinfo.quiet_collectors():
            b_inside.set()
            assert a_exited.wait(_TIMEOUT), "thread a never exited"
        b_may_exit.set()

    t_a = threading.Thread(target=thread_a)
    t_b = threading.Thread(target=thread_b)
    t_a.start()
    t_b.start()
    t_a.join(_TIMEOUT)
    t_b.join(_TIMEOUT)

    assert not t_a.is_alive() and not t_b.is_alive(), "threads did not finish -- deadlock"
    assert b_may_exit.is_set(), "thread b did not complete its with-block"
    assert root_logger.level == original_level, (
        "root logger level was left elevated after two overlapping "
        "quiet_collectors() calls -- config-server would stop logging "
        "permanently"
    )


def test_other_thread_logs_normally_during_an_active_collection(caplog):
    """The milder half of the same defect: even a single quiet_collectors()
    call, if implemented by raising the *root* logger's level, silences
    every other thread's logging for as long as collection takes (seconds,
    since it shells out to journalctl/dpkg-query) -- not just the
    collectors' own noise. A neighbouring route (or waitress itself, on
    its own thread) must keep logging normally while a collection is
    still in progress on another thread, not merely after it finishes.
    """
    caplog.set_level(logging.WARNING)

    collector_entered = threading.Event()
    collector_may_exit = threading.Event()

    def collector_thread():
        with supportinfo.quiet_collectors():
            logging.getLogger("configurator.systeminfo").warning(
                "collector noise that must be suppressed"
            )
            collector_entered.set()
            assert collector_may_exit.wait(_TIMEOUT), "test main thread never released us"

    t = threading.Thread(target=collector_thread)
    t.start()
    try:
        assert collector_entered.wait(_TIMEOUT), "collector thread never entered quiet_collectors()"
        # The collector thread is still inside the with-block right now.
        logging.getLogger("configurator.server").warning(
            "neighbouring route noise that must survive"
        )
    finally:
        collector_may_exit.set()
        t.join(_TIMEOUT)

    assert "collector noise that must be suppressed" not in caplog.text
    assert "neighbouring route noise that must survive" in caplog.text
