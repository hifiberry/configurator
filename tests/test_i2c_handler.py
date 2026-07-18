#!/usr/bin/env python3
"""Regression tests for I2C handler."""

import sys
import unittest
from unittest.mock import MagicMock, patch


class MockResponse:
    """Mock Flask response object."""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def get_json(self):
        """Return JSON payload."""
        return self.json_data

    def __iter__(self):
        """Support tuple unpacking for error responses."""
        return iter([self, self.status_code])


def mock_jsonify(data):
    """Mock Flask jsonify helper."""
    return MockResponse(data, 200)


flask_mock = MagicMock()
flask_mock.jsonify = mock_jsonify
flask_mock.request = MagicMock()
flask_mock.Response = MockResponse
sys.modules["flask"] = flask_mock

from src.handlers.i2c_handler import I2CHandler  # noqa: E402  # pylint: disable=wrong-import-position


class TestI2CHandler(unittest.TestCase):
    """Regression tests for I2C handler endpoint."""

    def setUp(self):
        """Set up handler under test."""
        self.handler = I2CHandler()

    @patch("src.handlers.i2c_handler.get_i2c_info")
    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_success_status(self, mock_request, mock_get_i2c_info):
        """Returns success when backend response has no error field."""
        mock_request.args.get.return_value = 1
        mock_get_i2c_info.return_value = {
            "bus_number": 1,
            "bus_exists": True,
            "detected_devices": ["0x48"],
        }

        response = self.handler.handle_get_i2c_devices()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["bus_number"], 1)

    @patch("src.handlers.i2c_handler.get_i2c_info")
    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_error_status_when_backend_has_error(
        self,
        mock_request,
        mock_get_i2c_info,
    ):
        """Returns error status when backend includes an error key."""
        mock_request.args.get.return_value = 1
        mock_get_i2c_info.return_value = {
            "bus_number": 1,
            "error": "I2C bus 1 not found",
        }

        response = self.handler.handle_get_i2c_devices()
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["data"]["error"], "I2C bus 1 not found")

    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_invalid_bus_negative(self, mock_request):
        """Rejects negative bus number."""
        mock_request.args.get.return_value = -1

        response, status_code = self.handler.handle_get_i2c_devices()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(data["status"], "error")
        self.assertIn("Invalid bus number", data["message"])

    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_invalid_bus_too_high(self, mock_request):
        """Rejects out-of-range bus numbers above 10."""
        mock_request.args.get.return_value = 11

        response, status_code = self.handler.handle_get_i2c_devices()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(data["status"], "error")
        self.assertIn("Invalid bus number", data["message"])

    @patch("src.handlers.i2c_handler.get_i2c_info")
    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_backend_exception_returns_500(
        self,
        mock_request,
        mock_get_i2c_info,
    ):
        """Returns 500 when backend scan raises an exception."""
        mock_request.args.get.return_value = 1
        mock_get_i2c_info.side_effect = RuntimeError("scan failed")

        response, status_code = self.handler.handle_get_i2c_devices()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Failed to scan I2C devices")
        self.assertEqual(data["error"], "scan failed")

    @patch("src.handlers.i2c_handler.get_i2c_info")
    @patch("src.handlers.i2c_handler.request")
    def test_get_i2c_devices_reads_bus_query_with_expected_parameters(
        self,
        mock_request,
        mock_get_i2c_info,
    ):
        """Uses bus query parameter with default and int conversion."""
        mock_request.args.get.return_value = 2
        mock_get_i2c_info.return_value = {"bus_number": 2}

        self.handler.handle_get_i2c_devices()

        mock_request.args.get.assert_called_once_with("bus", default=1, type=int)
        mock_get_i2c_info.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
