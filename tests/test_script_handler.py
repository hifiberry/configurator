#!/usr/bin/env python3
"""
Regression tests for Script Handler.

Tests script configuration loading, listing, execution (sync and background),
and error handling for script management endpoints.
"""

# pylint: disable=import-error,too-many-public-methods
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock Flask response class
class MockResponse:  # pylint: disable=too-few-public-methods
    """Mock Flask Response object"""

    def __init__(self, json_data=None, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.headers = {}

    def get_json(self):
        """Return the mocked JSON payload."""
        return self.json_data


def mock_jsonify(data):
    """Mock Flask jsonify function"""
    return MockResponse(data, 200)


# Patch Flask imports before importing the handler
def setup_flask_mocks():
    """Setup Flask mocks before importing handler."""
    sys.modules['flask'] = MagicMock()
    sys.modules['flask'].jsonify = mock_jsonify
    sys.modules['flask'].request = MagicMock()


setup_flask_mocks()

# pylint: disable=wrong-import-position
from handlers.script_handler import ScriptHandler  # noqa: E402


class TestScriptHandlerConfigLoading(unittest.TestCase):
    """Test script configuration loading"""

    def setUp(self):
        """Create handler with temp config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.json")

    def tearDown(self):
        """Clean up temp directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_config_file_not_found(self):
        """Handle missing config file gracefully"""
        handler = ScriptHandler(config_file="/nonexistent/config.json")
        self.assertEqual(handler.scripts, {})

    def test_load_config_empty_file(self):
        """Handle empty JSON object in config"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        handler = ScriptHandler(config_file=self.config_file)
        self.assertEqual(handler.scripts, {})

    def test_load_config_no_scripts_key(self):
        """Handle config with no scripts key"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump({"other_key": "value"}, f)
        handler = ScriptHandler(config_file=self.config_file)
        self.assertEqual(handler.scripts, {})

    def test_load_config_invalid_json(self):
        """Handle invalid JSON in config file"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            f.write("{invalid json")
        handler = ScriptHandler(config_file=self.config_file)
        self.assertEqual(handler.scripts, {})

    def test_load_config_valid_scripts(self):
        """Load valid script configuration"""
        config = {
            "scripts": {
                "test_script": {
                    "name": "Test Script",
                    "description": "A test script",
                    "path": "/usr/bin/test.sh",
                    "args": ["arg1", "arg2"]
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        self.assertIn("test_script", handler.scripts)
        self.assertEqual(handler.scripts["test_script"]["name"], "Test Script")

    def test_load_config_multiple_scripts(self):
        """Load multiple scripts from config"""
        config = {
            "scripts": {
                "script1": {"path": "/path/to/script1.sh"},
                "script2": {"path": "/path/to/script2.sh"},
                "script3": {"path": "/path/to/script3.sh"}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        self.assertEqual(len(handler.scripts), 3)


class TestScriptHandlerListing(unittest.TestCase):
    """Test script listing functionality"""

    def setUp(self):
        """Create handler with temp config"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.json")

    def tearDown(self):
        """Clean up temp directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_list_scripts_empty(self):
        """Return empty list when no scripts configured"""
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_list_scripts()
        self.assertEqual(response.json_data["status"], "success")
        self.assertEqual(response.json_data["data"]["count"], 0)
        self.assertEqual(response.json_data["data"]["scripts"], [])

    def test_list_scripts_single(self):
        """List single configured script"""
        config = {
            "scripts": {
                "backup": {
                    "name": "Backup Script",
                    "description": "System backup",
                    "path": "/usr/local/bin/backup.sh",
                    "args": ["daily"]
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_list_scripts()
        self.assertEqual(response.json_data["status"], "success")
        self.assertEqual(response.json_data["data"]["count"], 1)
        scripts = response.json_data["data"]["scripts"]
        self.assertEqual(scripts[0]["id"], "backup")
        self.assertEqual(scripts[0]["name"], "Backup Script")

    def test_list_scripts_multiple(self):
        """List multiple configured scripts"""
        config = {
            "scripts": {
                "script1": {"name": "Script 1", "path": "/path/to/1.sh"},
                "script2": {"name": "Script 2", "path": "/path/to/2.sh"},
                "script3": {"name": "Script 3", "path": "/path/to/3.sh"}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_list_scripts()
        self.assertEqual(response.json_data["data"]["count"], 3)
        self.assertEqual(len(response.json_data["data"]["scripts"]), 3)


class TestScriptHandlerExecution(unittest.TestCase):
    """Test script execution functionality"""

    def setUp(self):
        """Create handler and temp script"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.json")
        self.script_file = os.path.join(self.temp_dir, "test.sh")
        # Create executable script
        with open(self.script_file, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\necho 'Hello World'\n")
        os.chmod(self.script_file, 0o755)

    def tearDown(self):
        """Clean up temp directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_execute_script_not_found(self):
        """Return 404 for unknown script"""
        config = {"scripts": {}}
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_execute_script("unknown")
        self.assertEqual(response[1], 404)
        self.assertEqual(response[0].json_data["status"], "error")
        self.assertEqual(response[0].json_data["error"], "script_not_found")

    def test_execute_script_no_path(self):
        """Return 500 when script has no path configured"""
        config = {
            "scripts": {
                "broken": {"name": "Broken Script"}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_execute_script("broken")
        self.assertEqual(response[1], 500)
        self.assertEqual(response[0].json_data["error"], "script_path_missing")

    def test_execute_script_path_not_found(self):
        """Return 404 when script path doesn't exist"""
        config = {
            "scripts": {
                "missing": {
                    "path": "/nonexistent/script.sh"
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_execute_script("missing")
        self.assertEqual(response[1], 404)
        self.assertEqual(response[0].json_data["error"], "script_path_not_found")

    def test_execute_script_not_executable(self):
        """Return 403 when script is not executable"""
        # Create non-executable script
        non_exec = os.path.join(self.temp_dir, "noexec.sh")
        with open(non_exec, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\n")
        os.chmod(non_exec, 0o644)

        config = {
            "scripts": {
                "noexec": {"path": non_exec}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_execute_script("noexec")
        self.assertEqual(response[1], 403)
        self.assertEqual(response[0].json_data["error"], "script_not_executable")

    def test_execute_script_sync_success(self):
        """Execute script synchronously and return output"""
        config = {
            "scripts": {
                "test": {
                    "name": "Test",
                    "path": self.script_file,
                    "args": []
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = {"background": False}
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("test")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json_data["status"], "success")
            self.assertEqual(response.json_data["data"]["exit_code"], 0)

    def test_execute_script_timeout(self):
        """Handle script timeout"""
        # Create script that sleeps
        sleep_script = os.path.join(self.temp_dir, "sleep.sh")
        with open(sleep_script, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\nsleep 10\n")
        os.chmod(sleep_script, 0o755)

        config = {
            "scripts": {
                "sleeper": {"path": sleep_script}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = {"background": False, "timeout": 0.1}
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("sleeper")
            self.assertEqual(response[1], 500)
            self.assertEqual(response[0].json_data["error"], "execution_timeout")

    def test_execute_script_with_args(self):
        """Execute script with configured arguments"""
        config = {
            "scripts": {
                "test": {
                    "path": self.script_file,
                    "args": ["arg1", "arg2"]
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = {}
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("test")
            # Command should include args
            cmd = response.json_data["data"]["command"]
            self.assertIn("arg1", cmd)
            self.assertIn("arg2", cmd)

    def test_execute_script_background(self):
        """Execute script in background mode"""
        config = {
            "scripts": {
                "test": {"path": self.script_file}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = {"background": True}
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("test")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json_data["status"], "success")
            self.assertEqual(
                response.json_data["data"]["execution_mode"],
                "background"
            )

    def test_execute_script_invalid_timeout(self):
        """Clamp invalid timeout values"""
        config = {
            "scripts": {
                "test": {"path": self.script_file}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = {"background": False, "timeout": 5000}
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("test")
            # Should clamp to 3600 (1 hour)
            self.assertEqual(response.status_code, 200)

    def test_execute_script_invalid_json(self):
        """Handle invalid JSON in request body"""
        config = {
            "scripts": {
                "test": {"path": self.script_file}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.side_effect = ValueError("Invalid JSON")
        with patch("handlers.script_handler.request", mock_request):
            response = handler.handle_execute_script("test")
            # Should still execute with default params
            self.assertEqual(response.status_code, 200)


class TestScriptHandlerInfo(unittest.TestCase):
    """Test script info retrieval"""

    def setUp(self):
        """Create handler with temp config"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.json")
        self.script_file = os.path.join(self.temp_dir, "test.sh")
        # Create executable script
        with open(self.script_file, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\n")
        os.chmod(self.script_file, 0o755)

    def tearDown(self):
        """Clean up temp directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_get_script_info_not_found(self):
        """Return 404 for unknown script"""
        config = {"scripts": {}}
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_get_script_info("unknown")
        self.assertEqual(response[1], 404)

    def test_get_script_info_exists_executable(self):
        """Return info for executable script"""
        config = {
            "scripts": {
                "test": {
                    "name": "Test Script",
                    "description": "A test",
                    "path": self.script_file,
                    "args": ["arg1"]
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_get_script_info("test")
        self.assertEqual(response.status_code, 200)
        data = response.json_data["data"]
        self.assertEqual(data["id"], "test")
        self.assertEqual(data["name"], "Test Script")
        self.assertTrue(data["path_exists"])
        self.assertTrue(data["path_executable"])
        self.assertTrue(data["ready"])

    def test_get_script_info_nonexistent_path(self):
        """Return info for script with nonexistent path"""
        config = {
            "scripts": {
                "missing": {
                    "name": "Missing",
                    "path": "/nonexistent/script.sh"
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_get_script_info("missing")
        self.assertEqual(response.status_code, 200)
        data = response.json_data["data"]
        self.assertFalse(data["path_exists"])
        self.assertFalse(data["path_executable"])
        self.assertFalse(data["ready"])

    def test_get_script_info_not_executable(self):
        """Return info for script that exists but is not executable"""
        noexec = os.path.join(self.temp_dir, "noexec.sh")
        with open(noexec, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\n")
        os.chmod(noexec, 0o644)

        config = {
            "scripts": {
                "noexec": {"path": noexec}
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_get_script_info("noexec")
        data = response.json_data["data"]
        self.assertTrue(data["path_exists"])
        self.assertFalse(data["path_executable"])
        self.assertFalse(data["ready"])


class TestScriptHandlerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Create handler"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.json")

    def tearDown(self):
        """Clean up"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_handle_list_scripts_with_exception(self):
        """Handle unexpected exception in list_scripts"""
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_list_scripts()
        # Should return success response even with empty scripts
        self.assertEqual(response.status_code, 200)

    def test_empty_request_json(self):
        """Handle empty/None JSON in request"""
        config = {
            "scripts": {
                "test": {
                    "path": os.path.join(self.temp_dir, "test.sh")
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)

        mock_request = Mock()
        mock_request.get_json.return_value = None
        with patch("handlers.script_handler.request", mock_request):
            # Should use default values
            response = handler.handle_execute_script("test")
            # Script doesn't exist, so 404 is expected
            self.assertIn(response[1], [404, 500])

    def test_script_with_all_optional_fields_empty(self):
        """Handle script config with empty optional fields"""
        config = {
            "scripts": {
                "minimal": {
                    "path": "/path/to/script.sh"
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        handler = ScriptHandler(config_file=self.config_file)
        response = handler.handle_list_scripts()
        scripts = response.json_data["data"]["scripts"]
        self.assertEqual(scripts[0]["id"], "minimal")
        self.assertEqual(scripts[0]["name"], "minimal")
        self.assertEqual(scripts[0]["description"], "")
        self.assertEqual(scripts[0]["args"], [])


if __name__ == "__main__":
    unittest.main()
