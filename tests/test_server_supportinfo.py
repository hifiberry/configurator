# tests/test_server_supportinfo.py
import logging
from unittest.mock import patch

import pytest
flask = pytest.importorskip("flask", reason="Flask is absent in the build chroot")

from configurator.server import ConfigAPIServer


@pytest.fixture
def server():
    srv = ConfigAPIServer()
    srv.app.config["TESTING"] = True
    return srv


@pytest.fixture
def client(server):
    with server.app.test_client() as c:
        yield c


def test_supportinfo_returns_plain_text(client):
    with patch("configurator.supportinfo.build_report", return_value={"System": {"Pi Model": "Pi 5"}}), \
         patch("configurator.supportinfo.render_text", return_value="## System\nPi Model: Pi 5\n"):
        response = client.get("/api/v1/supportinfo")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "Pi Model: Pi 5" in response.get_data(as_text=True)


def test_supportinfo_uses_the_shared_cli_code_path(client):
    with patch("configurator.supportinfo.build_report", return_value={}) as build, \
         patch("configurator.supportinfo.render_text", return_value="") as render:
        client.get("/api/v1/supportinfo")
    build.assert_called_once()
    render.assert_called_once()


def test_supportinfo_failure_returns_500_without_leaking_details(client):
    boom = RuntimeError("/home/someuser/secret-path exploded")
    with patch("configurator.supportinfo.build_report", side_effect=boom):
        response = client.get("/api/v1/supportinfo")
    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert "someuser" not in body
    assert "secret-path" not in body


def test_supportinfo_endpoint_silences_collector_logging_during_collection(client):
    """setup_logging() is what keeps the CLI quiet; the endpoint does not
    call it (it must not permanently touch config-server's own logging --
    see the next test), so it needs its own, scoped way to silence the
    collectors' WARNING/ERROR noise for just this request. Simulates a
    collector emitting a WARNING mid-collection and asserts the root
    logger's effective level was raised enough to suppress it at the point
    of the call.
    """
    seen_level = {}

    def fake_build_report(*_a, **_kw):
        seen_level["effective"] = logging.getLogger().getEffectiveLevel()
        logging.getLogger("configurator.systeminfo").warning(
            "collector noise that must not reach config-server's journal"
        )
        return {}

    with patch("configurator.supportinfo.build_report", side_effect=fake_build_report), \
         patch("configurator.supportinfo.render_text", return_value=""):
        response = client.get("/api/v1/supportinfo")

    assert response.status_code == 200
    assert seen_level["effective"] >= logging.CRITICAL


def test_supportinfo_request_does_not_permanently_silence_other_routes(server, client, caplog):
    """The suppression above must be scoped to the one request -- a
    supportinfo call must not leave config-server's own logging quiet for
    every route that runs after it. Exercises supportinfo once (with a
    collector that logs, same as above), then hits a neighbouring route
    (systeminfo) that fails and logs its own error, and asserts that error
    is still captured -- proving the root logger's level was restored.
    """
    def fake_build_report(*_a, **_kw):
        logging.getLogger("configurator.systeminfo").warning("noise during supportinfo")
        return {}

    with patch("configurator.supportinfo.build_report", side_effect=fake_build_report), \
         patch("configurator.supportinfo.render_text", return_value=""):
        first = client.get("/api/v1/supportinfo")
    assert first.status_code == 200

    caplog.set_level(logging.ERROR, logger="configurator.server")
    boom = RuntimeError("systeminfo exploded")
    with patch.object(server.systeminfo, "get_system_info_dict", side_effect=boom):
        second = client.get("/api/v1/systeminfo")

    assert second.status_code == 500
    assert any(
        "Error getting system info" in record.message
        for record in caplog.records
    ), "neighbouring route's own error logging must survive a prior supportinfo request"
