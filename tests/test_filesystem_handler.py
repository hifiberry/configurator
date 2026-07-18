#!/usr/bin/env python3
"""Regression tests for filesystem handler."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class MockResponse:
    """Mock Flask response object used by tests."""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def get_json(self):
        """Return JSON payload."""
        return self.json_data

    def __iter__(self):
        """Support tuple-style unpacking used by handler responses."""
        return iter([self, self.status_code])


def mock_jsonify(data):
    """Mock Flask jsonify function."""
    return MockResponse(data, 200)


flask_mock = MagicMock()
flask_mock.jsonify = mock_jsonify
flask_mock.request = MagicMock()
flask_mock.Response = MockResponse
sys.modules["flask"] = flask_mock

from src.handlers.filesystem_handler import FilesystemHandler  # pylint: disable=wrong-import-position  # noqa: E402


class TestFilesystemHandlerConfigLoading(unittest.TestCase):
    """Tests for configuration loading behavior."""

    def test_load_config_missing_file_uses_defaults(self):
        """Missing config file should set safe defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "missing.json")
            handler = FilesystemHandler(config_file=config_path)

            self.assertEqual(handler.allowed_symlink_destinations, [])
            self.assertEqual(handler.allowed_exists_check_destinations, ["/etc"])

    def test_load_config_reads_allowed_destinations(self):
        """Valid config should populate destination allowlists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            payload = {
                "filesystem": {
                    "allowed_symlink_destinations": ["/opt/data", "/tmp"],
                    "allowed_exists_check_destinations": ["/etc", "/var"],
                }
            }
            with open(config_path, "w", encoding="utf-8") as config_file:
                json.dump(payload, config_file)

            handler = FilesystemHandler(config_file=config_path)

            self.assertEqual(handler.allowed_symlink_destinations, ["/opt/data", "/tmp"])
            self.assertEqual(handler.allowed_exists_check_destinations, ["/etc", "/var"])

    def test_load_config_without_filesystem_section_uses_defaults(self):
        """Config without filesystem section should fall back to defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w", encoding="utf-8") as config_file:
                json.dump({"other": {"value": 1}}, config_file)

            handler = FilesystemHandler(config_file=config_path)

            self.assertEqual(handler.allowed_symlink_destinations, [])
            self.assertEqual(handler.allowed_exists_check_destinations, ["/etc"])

    @patch("src.handlers.filesystem_handler.json.load", side_effect=ValueError("bad json"))
    def test_load_config_parse_error_uses_defaults(self, _mock_json_load):
        """Invalid JSON should gracefully fall back to defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
            config_path = tmp_file.name

        try:
            handler = FilesystemHandler(config_file=config_path)
            self.assertEqual(handler.allowed_symlink_destinations, [])
            self.assertEqual(handler.allowed_exists_check_destinations, ["/etc"])
        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)


class TestFilesystemHandlerListSymlinks(unittest.TestCase):
    """Tests for list symlinks endpoint."""

    def setUp(self):
        """Create handler with controlled allowlist."""
        self.handler = FilesystemHandler(config_file="/does/not/exist")

    @patch("src.handlers.filesystem_handler.request")
    def test_non_json_request_returns_400(self, mock_request):
        """Requests without JSON content type should fail."""
        mock_request.is_json = False

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(data["status"], "error")

    @patch("src.handlers.filesystem_handler.request")
    def test_missing_body_returns_400(self, mock_request):
        """Empty JSON body should fail validation."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Missing request body", data["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_missing_directory_returns_400(self, mock_request):
        """Missing directory field should be rejected."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"other": "value"}

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertIn("Missing required field: directory", data["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_no_allowed_destinations_returns_403(self, mock_request):
        """Empty allowlist should deny access."""
        self.handler.allowed_symlink_destinations = []
        mock_request.is_json = True
        mock_request.get_json.return_value = {"directory": "/tmp"}

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 403)
        self.assertEqual(data["error"], "directory_access_not_allowed")

    @patch("src.handlers.filesystem_handler.request")
    def test_directory_not_allowed_returns_403(self, mock_request):
        """Directories outside allowlist should be denied."""
        self.handler.allowed_symlink_destinations = ["/allowed"]
        mock_request.is_json = True
        mock_request.get_json.return_value = {"directory": "/not-allowed/dir"}

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 403)
        self.assertEqual(data["error"], "directory_not_allowed")

    @patch("src.handlers.filesystem_handler.request")
    def test_missing_directory_path_returns_404(self, mock_request):
        """Non-existent directory should return 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_dir = os.path.join(tmpdir, "missing")
            self.handler.allowed_symlink_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": missing_dir}

            response, status_code = self.handler.handle_list_symlinks()
            data = response.get_json()

            self.assertEqual(status_code, 404)
            self.assertIn("Directory does not exist", data["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_path_not_directory_returns_400(self, mock_request):
        """File path instead of directory should return 400."""
        with tempfile.NamedTemporaryFile() as tmp_file:
            self.handler.allowed_symlink_destinations = [os.path.dirname(tmp_file.name)]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": tmp_file.name}

            response, status_code = self.handler.handle_list_symlinks()
            data = response.get_json()

            self.assertEqual(status_code, 400)
            self.assertIn("Path is not a directory", data["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_permission_denied_returns_403(self, mock_request):
        """PermissionError while listing directory should return 403."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.handler.allowed_symlink_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": tmpdir}

            with patch("src.handlers.filesystem_handler.os.listdir", side_effect=PermissionError):
                response, status_code = self.handler.handle_list_symlinks()

            data = response.get_json()
            self.assertEqual(status_code, 403)
            self.assertIn("Permission denied", data["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_list_symlinks_success_and_sorting(self, mock_request):
        """Successful listing should return sorted symlink entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_a = os.path.join(tmpdir, "target_a.txt")
            target_b = os.path.join(tmpdir, "target_b.txt")
            link_a = os.path.join(tmpdir, "a-link")
            link_b = os.path.join(tmpdir, "B-link")

            with open(target_a, "w", encoding="utf-8") as file_a:
                file_a.write("a")
            with open(target_b, "w", encoding="utf-8") as file_b:
                file_b.write("b")

            os.symlink(target_a, link_a)
            os.symlink(target_b, link_b)

            self.handler.allowed_symlink_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": tmpdir}

            response = self.handler.handle_list_symlinks()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["data"]["count"], 2)
            names = [entry["name"] for entry in data["data"]["symlinks"]]
            self.assertEqual(names, ["a-link", "B-link"])

    @patch("src.handlers.filesystem_handler.request")
    def test_symlink_read_error_is_reported(self, mock_request):
        """Unreadable symlink target should be reported as an item error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            link_path = os.path.join(tmpdir, "bad-link")
            os.symlink("/tmp/target", link_path)

            self.handler.allowed_symlink_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": tmpdir}

            original_readlink = os.readlink

            def readlink_side_effect(path):
                if path == link_path:
                    raise OSError("cannot read")
                return original_readlink(path)

            with patch(
                "src.handlers.filesystem_handler.os.readlink",
                side_effect=readlink_side_effect,
            ):
                response = self.handler.handle_list_symlinks()

            data = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["data"]["count"], 1)
            self.assertIn("Cannot read symlink target", data["data"]["symlinks"][0]["error"])

    @patch("src.handlers.filesystem_handler.request")
    def test_symlink_lstat_error_is_reported(self, mock_request):
        """lstat failure should return entry with limited symlink info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "target")
            link_path = os.path.join(tmpdir, "link")

            with open(target_path, "w", encoding="utf-8") as target_file:
                target_file.write("x")
            os.symlink(target_path, link_path)

            self.handler.allowed_symlink_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"directory": tmpdir}

            original_lstat = os.lstat
            original_islink = os.path.islink

            def lstat_side_effect(path):
                if path == link_path:
                    raise OSError("cannot stat")
                return original_lstat(path)

            def islink_side_effect(path):
                if path == link_path:
                    return True
                return original_islink(path)

            with patch(
                "src.handlers.filesystem_handler.os.path.islink",
                side_effect=islink_side_effect,
            ):
                with patch(
                    "src.handlers.filesystem_handler.os.lstat",
                    side_effect=lstat_side_effect,
                ):
                    response = self.handler.handle_list_symlinks()

            data = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertIn("Cannot access symlink info", data["data"]["symlinks"][0]["error"])

    @patch("src.handlers.filesystem_handler.request")
    def test_request_json_parse_error_returns_500(self, mock_request):
        """Unexpected request parsing errors should return 500."""
        self.handler.allowed_symlink_destinations = ["/tmp"]
        mock_request.is_json = True
        mock_request.get_json.side_effect = RuntimeError("request parse failure")

        response, status_code = self.handler.handle_list_symlinks()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "request parse failure")


class TestFilesystemHandlerFileExists(unittest.TestCase):
    """Tests for file-exists endpoint."""

    def setUp(self):
        """Create handler with controlled allowlist."""
        self.handler = FilesystemHandler(config_file="/does/not/exist")

    @patch("src.handlers.filesystem_handler.request")
    def test_non_json_request_returns_400(self, mock_request):
        """Requests without JSON content type should fail."""
        mock_request.is_json = False

        response, status_code = self.handler.handle_file_exists()
        self.assertEqual(status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    @patch("src.handlers.filesystem_handler.request")
    def test_missing_body_returns_400(self, mock_request):
        """Empty body should return validation error."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {}

        response, status_code = self.handler.handle_file_exists()
        self.assertEqual(status_code, 400)
        self.assertIn("Missing request body", response.get_json()["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_missing_path_returns_400(self, mock_request):
        """Missing path field should return validation error."""
        mock_request.is_json = True
        mock_request.get_json.return_value = {"other": "value"}

        response, status_code = self.handler.handle_file_exists()
        self.assertEqual(status_code, 400)
        self.assertIn("Missing required field: path", response.get_json()["message"])

    @patch("src.handlers.filesystem_handler.request")
    def test_no_allowed_destinations_returns_403(self, mock_request):
        """Empty file-exists allowlist should deny access."""
        self.handler.allowed_exists_check_destinations = []
        mock_request.is_json = True
        mock_request.get_json.return_value = {"path": "/etc/passwd"}

        response, status_code = self.handler.handle_file_exists()
        self.assertEqual(status_code, 403)
        self.assertEqual(response.get_json()["error"], "file_access_not_allowed")

    @patch("src.handlers.filesystem_handler.request")
    def test_path_not_allowed_returns_403(self, mock_request):
        """Paths outside allowlist should be rejected."""
        self.handler.allowed_exists_check_destinations = ["/allowed"]
        mock_request.is_json = True
        mock_request.get_json.return_value = {"path": "/etc/passwd"}

        response, status_code = self.handler.handle_file_exists()
        self.assertEqual(status_code, 403)
        self.assertEqual(response.get_json()["error"], "path_not_allowed")

    @patch("src.handlers.filesystem_handler.request")
    def test_path_exists_returns_success_true(self, mock_request):
        """Existing path should return success with exists=true."""
        self.handler.allowed_exists_check_destinations = ["/tmp"]

        with tempfile.NamedTemporaryFile() as tmp_file:
            mock_request.is_json = True
            mock_request.get_json.return_value = {"path": tmp_file.name}

            response = self.handler.handle_file_exists()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["status"], "success")
            self.assertTrue(data["data"]["exists"])

    @patch("src.handlers.filesystem_handler.request")
    def test_path_missing_returns_success_false(self, mock_request):
        """Missing path should return success with exists=false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "missing")
            self.handler.allowed_exists_check_destinations = [tmpdir]
            mock_request.is_json = True
            mock_request.get_json.return_value = {"path": missing_path}

            response = self.handler.handle_file_exists()
            data = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertFalse(data["data"]["exists"])

    @patch("src.handlers.filesystem_handler.request")
    def test_os_error_returns_500(self, mock_request):
        """Unexpected exception should return 500 response."""
        self.handler.allowed_exists_check_destinations = ["/tmp"]
        mock_request.is_json = True
        mock_request.get_json.return_value = {"path": "/tmp/file"}

        with patch(
            "src.handlers.filesystem_handler.os.path.exists",
            side_effect=RuntimeError("boom"),
        ):
            response, status_code = self.handler.handle_file_exists()

        data = response.get_json()
        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "boom")

    @patch("src.handlers.filesystem_handler.request")
    def test_request_json_parse_error_returns_500(self, mock_request):
        """Unexpected request parsing errors should return 500."""
        self.handler.allowed_exists_check_destinations = ["/tmp"]
        mock_request.is_json = True
        mock_request.get_json.side_effect = RuntimeError("request parse failure")

        response, status_code = self.handler.handle_file_exists()
        data = response.get_json()

        self.assertEqual(status_code, 500)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "request parse failure")


if __name__ == "__main__":
    unittest.main()
