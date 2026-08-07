# tests/test_server_supportinfo.py
from unittest.mock import patch

import pytest

from configurator.server import ConfigAPIServer


@pytest.fixture
def client():
    server = ConfigAPIServer()
    server.app.config["TESTING"] = True
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
