#!/usr/bin/env python3
"""Regression tests for hostname API handler."""

import sys
import unittest
from unittest.mock import MagicMock, patch


class MockResponse:
    """Mock Flask response for handler tests."""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def get_json(self):
        """Return response payload."""
        return self.json_data

    def __iter__(self):
        """Support tuple unpacking in tests."""
        return iter([self, self.status_code])


def mock_jsonify(data):
    """Mock Flask jsonify."""
    return MockResponse(data, 200)


flask_mock = MagicMock()
flask_mock.jsonify = mock_jsonify
flask_mock.request = MagicMock()
flask_mock.Response = MockResponse
sys.modules["flask"] = flask_mock

from src.handlers.hostname_handler import HostnameHandler  # pylint: disable=wrong-import-position  # noqa: E402


class TestHostnameHandlerGetHostname(unittest.TestCase):
    """Tests for hostname retrieval endpoint."""

    def setUp(self):
        """Create handler instance."""
        self.handler = HostnameHandler()

    @patch("src.handlers.hostname_handler.get_hostnames_with_fallback")
    def test_get_hostname_success(self, mock_get_hostnames):
        """Should return current hostname data on success."""
        mock_get_hostnames.return_value = ("hifiberry", "HiFiBerry")

        response = self.handler.handle_get_hostname()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["hostname"], "hifiberry")
        self.assertEqual(data["data"]["pretty_hostname"], "HiFiBerry")

    @patch("src.handlers.hostname_handler.get_hostnames_with_fallback")
    def test_get_hostname_none_returns_500(self, mock_get_hostnames):
        """Should return error when hostname lookup fails."""
        mock_get_hostnames.return_value = (None, None)

        response, status_code = self.handler.handle_get_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertIn("Failed to retrieve", data["message"])

    @patch("src.handlers.hostname_handler.get_hostnames_with_fallback")
    def test_get_hostname_exception_returns_500(self, mock_get_hostnames):
        """Should return 500 when unexpected errors occur."""
        mock_get_hostnames.side_effect = RuntimeError("lookup failed")

        response, status_code = self.handler.handle_get_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "lookup failed")

    @patch("src.handlers.hostname_handler.get_hostnames_with_fallback")
    def test_get_hostname_fallback_without_flask(self, mock_get_hostnames):
        """Should return dict payload when Flask jsonify is unavailable."""
        mock_get_hostnames.return_value = ("hifiberry", "HiFiBerry")

        with patch("src.handlers.hostname_handler.jsonify", None):
            response = self.handler.handle_get_hostname()

        self.assertIsInstance(response, dict)
        self.assertEqual(response["status"], "success")


class TestHostnameHandlerSetHostnameValidation(unittest.TestCase):
    """Tests for request/validation failures in set endpoint."""

    def setUp(self):
        """Create handler instance."""
        self.handler = HostnameHandler()

    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_non_json_returns_400(self, mock_request):
        """Requests without JSON content should fail."""
        mock_request.is_json = False

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(data["status"], "error")
        self.assertIn("Content-Type", data["message"])

    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_missing_body_returns_400(self, mock_request):
        """Missing body should fail validation."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Missing request body", data["message"])

    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_requires_one_field(self, mock_request):
        """Must provide hostname or pretty_hostname."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"other": "value"}

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Must provide either", data["message"])

    @patch("src.handlers.hostname_handler.validate_pretty_hostname")
    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_invalid_pretty_returns_400(self, mock_request, mock_validate_pretty):
        """Invalid pretty hostname should be rejected."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"pretty_hostname": "***"}
        mock_validate_pretty.return_value = False

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Invalid pretty hostname", data["message"])

    @patch("src.handlers.hostname_handler.validate_hostname")
    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_invalid_hostname_returns_400(self, mock_request, mock_validate):
        """Invalid normalized hostname should be rejected."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"hostname": "bad@@host"}
        mock_validate.return_value = False

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Invalid hostname format", data["message"])


class TestHostnameHandlerSetHostnameBehavior(unittest.TestCase):
    """Tests for behavior and side effects in set endpoint."""

    def setUp(self):
        """Create handler instance."""
        self.handler = HostnameHandler()

    @patch("src.handlers.hostname_handler.get_hostnames_with_fallback")
    @patch("src.handlers.hostname_handler.set_hostname_with_hosts_update")
    @patch("src.handlers.hostname_handler.validate_hostname")
    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_success_hostname_only(
        self,
        mock_request,
        mock_validate_hostname,
        mock_set_hostname,
        mock_get_hostnames,
    ):
        """Hostname-only update should return success payload."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"hostname": "new-host"}
        mock_validate_hostname.return_value = True
        mock_set_hostname.return_value = True
        mock_get_hostnames.return_value = ("new-host", "New Host")

        response = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "success")
        mock_set_hostname.assert_called_once_with("new-host")

    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_success_pretty_only_derives_hostname(self, mock_request):
        """Pretty-only update should sanitize and set both hostnames."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"pretty_hostname": "My Device"}
        with (
            patch(
                "src.handlers.hostname_handler.validate_pretty_hostname",
                return_value=True,
            ),
            patch(
                "src.handlers.hostname_handler.sanitize_hostname",
                return_value="my-device",
            ) as mock_sanitize,
            patch("src.handlers.hostname_handler.validate_hostname", return_value=True),
            patch(
                "src.handlers.hostname_handler.set_hostname_with_hosts_update",
                return_value=True,
            ) as mock_set_hostname,
            patch(
                "src.handlers.hostname_handler.set_pretty_hostname",
                return_value=True,
            ) as mock_set_pretty,
            patch(
                "src.handlers.hostname_handler.get_hostnames_with_fallback",
                return_value=("my-device", "My Device"),
            ),
        ):
            response = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "success")
        mock_sanitize.assert_called_once_with("My Device")
        mock_set_hostname.assert_called_once_with("my-device")
        mock_set_pretty.assert_called_once_with("My Device")

    @patch("src.handlers.hostname_handler.set_pretty_hostname")
    @patch("src.handlers.hostname_handler.set_hostname_with_hosts_update")
    @patch("src.handlers.hostname_handler.validate_hostname")
    @patch("src.handlers.hostname_handler.validate_pretty_hostname")
    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_hostname_failure_returns_500_and_skips_pretty(
        self,
        mock_request,
        mock_validate_pretty,
        mock_validate_hostname,
        mock_set_hostname,
        mock_set_pretty,
    ):
        """If hostname set fails, pretty hostname update should not run."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            "hostname": "new-host",
            "pretty_hostname": "New Host",
        }
        mock_validate_pretty.return_value = True
        mock_validate_hostname.return_value = True
        mock_set_hostname.return_value = False

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        mock_set_pretty.assert_not_called()

    @patch("src.handlers.hostname_handler.set_pretty_hostname")
    @patch("src.handlers.hostname_handler.set_hostname_with_hosts_update")
    @patch("src.handlers.hostname_handler.validate_hostname")
    @patch("src.handlers.hostname_handler.validate_pretty_hostname")
    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_pretty_failure_returns_500(
        self,
        mock_request,
        mock_validate_pretty,
        mock_validate_hostname,
        mock_set_hostname,
        mock_set_pretty,
    ):
        """Pretty hostname update failure should return 500."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {
            "hostname": "new-host",
            "pretty_hostname": "New Host",
        }
        mock_validate_pretty.return_value = True
        mock_validate_hostname.return_value = True
        mock_set_hostname.return_value = True
        mock_set_pretty.return_value = False

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertIn("Failed to update hostname", data["message"])

    @patch("src.handlers.hostname_handler.request")
    def test_set_hostname_exception_returns_500(self, mock_request):
        """Unexpected errors should return 500."""
        mock_request.is_json = True
        mock_request.get_json.side_effect = RuntimeError("request parse failed")

        response, status_code = self.handler.handle_set_hostname()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "request parse failed")

    @patch("src.handlers.hostname_handler.request", None)
    @patch("src.handlers.hostname_handler.jsonify", None)
    def test_set_hostname_fallback_without_flask(self):
        """Should return dict payload when Flask objects are unavailable."""
        response = self.handler.handle_set_hostname()

        self.assertIsInstance(response, dict)
        self.assertEqual(response["status"], "error")
        self.assertIn("Content-Type", response["message"])


if __name__ == "__main__":
    unittest.main()
