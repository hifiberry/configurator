#!/usr/bin/env python3
"""
Regression tests for DSP Toolkit module

Tests cover:
- DSPToolkit initialization
- DSP detection with various scenarios
- Status checking methods
- Error handling and edge cases
- Convenience functions
- Command-line interface
"""

import unittest
import json
import sys
from unittest.mock import patch, MagicMock
from io import StringIO

# Add src directory to path for imports
sys.path.insert(0, '/home/ulf/data/configurator')

from src.dsptoolkit import (
    DSPToolkit, detect_dsp, get_detected_dsp_name, is_dsp_detected,
    DEFAULT_DSP_HOST, DEFAULT_DSP_PORT, DEFAULT_TIMEOUT
)


class TestDSPToolkitInitialization(unittest.TestCase):
    """Test DSPToolkit class initialization"""

    def test_default_initialization(self):
        """Test initialization with default parameters"""
        toolkit = DSPToolkit()
        self.assertEqual(toolkit.host, DEFAULT_DSP_HOST)
        self.assertEqual(toolkit.port, DEFAULT_DSP_PORT)
        self.assertEqual(toolkit.timeout, DEFAULT_TIMEOUT)
        self.assertEqual(toolkit.base_url, f"http://{DEFAULT_DSP_HOST}:{DEFAULT_DSP_PORT}")

    def test_custom_initialization(self):
        """Test initialization with custom parameters"""
        toolkit = DSPToolkit(host="192.168.1.100", port=8080, timeout=10.0)
        self.assertEqual(toolkit.host, "192.168.1.100")
        self.assertEqual(toolkit.port, 8080)
        self.assertEqual(toolkit.timeout, 10.0)
        self.assertEqual(toolkit.base_url, "http://192.168.1.100:8080")

    def test_partial_custom_initialization(self):
        """Test initialization with some custom parameters"""
        toolkit = DSPToolkit(host="10.0.0.1")
        self.assertEqual(toolkit.host, "10.0.0.1")
        self.assertEqual(toolkit.port, DEFAULT_DSP_PORT)
        self.assertEqual(toolkit.timeout, DEFAULT_TIMEOUT)


class TestDSPDetection(unittest.TestCase):
    """Test DSP detection functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.toolkit = DSPToolkit()
        self.valid_response = {"detected_dsp": "ADAU14xx", "status": "detected"}

    @patch('requests.get')
    def test_detect_dsp_success(self, mock_get):
        """Test successful DSP detection"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.valid_response
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertEqual(result, self.valid_response)
        mock_get.assert_called_once_with(
            "http://localhost:13141/hardware/dsp",
            timeout=DEFAULT_TIMEOUT
        )

    @patch('requests.get')
    def test_detect_dsp_not_detected(self, mock_get):
        """Test DSP detection when DSP is not present"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "not_detected"}
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "not_detected")

    @patch('requests.get')
    def test_detect_dsp_connection_error(self, mock_get):
        """Test DSP detection with connection error"""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_timeout(self, mock_get):
        """Test DSP detection with request timeout"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_invalid_json(self, mock_get):
        """Test DSP detection with invalid JSON response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_http_error(self, mock_get):
        """Test DSP detection with HTTP error status"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_404_not_found(self, mock_get):
        """Test DSP detection with 404 response"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_request_exception(self, mock_get):
        """Test DSP detection with generic request exception"""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Unknown error")

        result = self.toolkit.detect_dsp()
        self.assertIsNone(result)

    @patch('requests.get')
    def test_detect_dsp_empty_response(self, mock_get):
        """Test DSP detection with empty JSON response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertEqual(result, {})


class TestGetDetectedDSPName(unittest.TestCase):
    """Test get_detected_dsp_name method"""

    def setUp(self):
        """Set up test fixtures"""
        self.toolkit = DSPToolkit()

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_success(self, mock_detect):
        """Test getting DSP name when detected"""
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertEqual(name, "ADAU14xx")

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_not_detected(self, mock_detect):
        """Test getting DSP name when not detected"""
        mock_detect.return_value = {"status": "not_detected"}
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertIsNone(name)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_unavailable(self, mock_detect):
        """Test getting DSP name when service is unavailable"""
        mock_detect.return_value = None
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertIsNone(name)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_missing_field(self, mock_detect):
        """Test getting DSP name when detected_dsp field is missing"""
        mock_detect.return_value = {"status": "detected"}
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertIsNone(name)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_type_safety(self, mock_detect):
        """Test type safety when detected_dsp is not a string"""
        mock_detect.return_value = {"detected_dsp": 123, "status": "detected"}
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertIsNone(name)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_detected_dsp_name_none_value(self, mock_detect):
        """Test getting DSP name when detected_dsp is None"""
        mock_detect.return_value = {"detected_dsp": None, "status": "detected"}
        
        name = self.toolkit.get_detected_dsp_name()
        self.assertIsNone(name)


class TestIsDSPDetected(unittest.TestCase):
    """Test is_dsp_detected method"""

    def setUp(self):
        """Set up test fixtures"""
        self.toolkit = DSPToolkit()

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_is_dsp_detected_true(self, mock_detect):
        """Test is_dsp_detected returns True when DSP is detected"""
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        result = self.toolkit.is_dsp_detected()
        self.assertTrue(result)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_is_dsp_detected_false_not_detected(self, mock_detect):
        """Test is_dsp_detected returns False when DSP is not detected"""
        mock_detect.return_value = {"status": "not_detected"}
        
        result = self.toolkit.is_dsp_detected()
        self.assertFalse(result)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_is_dsp_detected_false_unavailable(self, mock_detect):
        """Test is_dsp_detected returns False when service is unavailable"""
        mock_detect.return_value = None
        
        result = self.toolkit.is_dsp_detected()
        self.assertFalse(result)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_is_dsp_detected_false_wrong_status(self, mock_detect):
        """Test is_dsp_detected returns False for non-detected status"""
        mock_detect.return_value = {"status": "error"}
        
        result = self.toolkit.is_dsp_detected()
        self.assertFalse(result)


class TestGetDSPStatus(unittest.TestCase):
    """Test get_dsp_status method"""

    def setUp(self):
        """Set up test fixtures"""
        self.toolkit = DSPToolkit()

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_dsp_status_detected(self, mock_detect):
        """Test getting status when DSP is detected"""
        mock_detect.return_value = {"status": "detected"}
        
        status = self.toolkit.get_dsp_status()
        self.assertEqual(status, "detected")

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_dsp_status_not_detected(self, mock_detect):
        """Test getting status when DSP is not detected"""
        mock_detect.return_value = {"status": "not_detected"}
        
        status = self.toolkit.get_dsp_status()
        self.assertEqual(status, "not_detected")

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_dsp_status_unavailable(self, mock_detect):
        """Test getting status when service is unavailable"""
        mock_detect.return_value = None
        
        status = self.toolkit.get_dsp_status()
        self.assertEqual(status, "unavailable")

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_dsp_status_error(self, mock_detect):
        """Test getting status when response is missing status field"""
        mock_detect.return_value = {}
        
        status = self.toolkit.get_dsp_status()
        self.assertEqual(status, "error")

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_get_dsp_status_custom_status(self, mock_detect):
        """Test getting custom status values"""
        mock_detect.return_value = {"status": "custom_status"}
        
        status = self.toolkit.get_dsp_status()
        self.assertEqual(status, "custom_status")


class TestConvenienceFunctions(unittest.TestCase):
    """Test module-level convenience functions"""

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    def test_convenience_detect_dsp(self, mock_detect):
        """Test convenience detect_dsp function"""
        expected = {"detected_dsp": "ADAU14xx", "status": "detected"}
        mock_detect.return_value = expected
        
        result = detect_dsp()
        self.assertEqual(result, expected)

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    def test_convenience_get_detected_dsp_name(self, mock_detect):
        """Test convenience get_detected_dsp_name function"""
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        name = get_detected_dsp_name()
        self.assertEqual(name, "ADAU14xx")

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    def test_convenience_is_dsp_detected(self, mock_detect):
        """Test convenience is_dsp_detected function"""
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        result = is_dsp_detected()
        self.assertTrue(result)

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    def test_convenience_functions_with_custom_params(self, mock_detect):
        """Test convenience functions with custom host/port/timeout"""
        expected = {"detected_dsp": "ADAU14xx", "status": "detected"}
        mock_detect.return_value = expected
        
        result = detect_dsp(host="10.0.0.1", port=8080, timeout=15.0)
        self.assertEqual(result, expected)


class TestMainCommandLine(unittest.TestCase):
    """Test main command-line interface"""

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--name-only'])
    def test_main_name_only_detected(self, mock_detect):
        """Test main with --name-only when DSP is detected"""
        from src.dsptoolkit import main
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), "ADAU14xx")

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--name-only'])
    def test_main_name_only_not_detected(self, mock_detect):
        """Test main with --name-only when DSP is not detected"""
        from src.dsptoolkit import main
        mock_detect.return_value = None
        
        result = main()
        self.assertEqual(result, 1)

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--status-only'])
    def test_main_status_only_detected(self, mock_detect):
        """Test main with --status-only when DSP is detected"""
        from src.dsptoolkit import main
        mock_detect.return_value = {"status": "detected"}
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertEqual(fake_out.getvalue().strip(), "detected")

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--status-only'])
    def test_main_status_only_not_detected(self, mock_detect):
        """Test main with --status-only when DSP is not detected"""
        from src.dsptoolkit import main
        mock_detect.return_value = {"status": "not_detected"}
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 1)
            self.assertEqual(fake_out.getvalue().strip(), "not_detected")

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--json'])
    def test_main_json_output(self, mock_detect):
        """Test main with --json output"""
        from src.dsptoolkit import main
        expected = {"detected_dsp": "ADAU14xx", "status": "detected"}
        mock_detect.return_value = expected
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            output_json = json.loads(fake_out.getvalue())
            self.assertEqual(output_json, expected)

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit', '--json'])
    def test_main_json_unavailable(self, mock_detect):
        """Test main with --json when service is unavailable"""
        from src.dsptoolkit import main
        mock_detect.return_value = None
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 1)
            output_json = json.loads(fake_out.getvalue())
            self.assertEqual(output_json.get("status"), "unavailable")

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit'])
    def test_main_default_output_detected(self, mock_detect):
        """Test main with default output when DSP is detected"""
        from src.dsptoolkit import main
        mock_detect.return_value = {"detected_dsp": "ADAU14xx", "status": "detected"}
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 0)
            self.assertIn("ADAU14xx", fake_out.getvalue())

    @patch('src.dsptoolkit.DSPToolkit.detect_dsp')
    @patch('sys.argv', ['dsptoolkit'])
    def test_main_default_output_unavailable(self, mock_detect):
        """Test main with default output when service is unavailable"""
        from src.dsptoolkit import main
        mock_detect.return_value = None
        
        with patch('sys.stdout', new=StringIO()) as fake_out:
            result = main()
            self.assertEqual(result, 1)
            self.assertIn("unavailable", fake_out.getvalue())

    @patch('src.dsptoolkit.DSPToolkit')
    @patch('sys.argv', ['dsptoolkit', '--host', '10.0.0.1', '--port', '8080', '--timeout', '20.0'])
    def test_main_custom_parameters(self, mock_toolkit_class):
        """Test main with custom host/port/timeout parameters"""
        from src.dsptoolkit import main
        mock_instance = MagicMock()
        mock_toolkit_class.return_value = mock_instance
        mock_instance.detect_dsp.return_value = {"status": "detected"}
        
        with patch('sys.stdout', new=StringIO()):
            main()
        
        mock_toolkit_class.assert_called_once_with("10.0.0.1", 8080, 20.0)


class TestEdgeCasesAndRobustness(unittest.TestCase):
    """Test edge cases and robustness"""

    def setUp(self):
        """Set up test fixtures"""
        self.toolkit = DSPToolkit()

    @patch('requests.get')
    def test_detect_dsp_large_timeout(self, mock_get):
        """Test DSP detection with very large timeout value"""
        toolkit = DSPToolkit(timeout=1000.0)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "detected"}
        mock_get.return_value = mock_response

        result = toolkit.detect_dsp()
        self.assertIsNotNone(result)

    @patch('requests.get')
    def test_detect_dsp_special_characters_in_response(self, mock_get):
        """Test DSP detection with special characters in response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "detected_dsp": "ADAU14xx-ñ-中文",
            "status": "detected"
        }
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNotNone(result)
        self.assertIn("detected_dsp", result)

    @patch('requests.get')
    def test_detect_dsp_extra_fields_in_response(self, mock_get):
        """Test DSP detection with extra fields in response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "detected_dsp": "ADAU14xx",
            "status": "detected",
            "version": "1.0",
            "extra_field": "extra_value"
        }
        mock_get.return_value = mock_response

        result = self.toolkit.detect_dsp()
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)

    @patch('requests.get')
    def test_detect_dsp_numeric_status_code(self, mock_get):
        """Test DSP detection with numeric status code boundary"""
        for status_code in [199, 201, 299]:
            with self.subTest(status_code=status_code):
                mock_response = MagicMock()
                mock_response.status_code = status_code
                mock_response.json.return_value = {"status": "detected"}
                mock_get.return_value = mock_response

                result = self.toolkit.detect_dsp()
                self.assertIsNone(result)

    def test_default_constants_are_correct(self):
        """Test that default constants have expected values"""
        self.assertEqual(DEFAULT_DSP_HOST, "localhost")
        self.assertEqual(DEFAULT_DSP_PORT, 13141)
        self.assertEqual(DEFAULT_TIMEOUT, 5.0)

    @patch.object(DSPToolkit, 'detect_dsp')
    def test_multiple_sequential_detections(self, mock_detect):
        """Test multiple sequential DSP detection calls"""
        mock_detect.return_value = {"status": "detected"}
        
        for _ in range(5):
            result = self.toolkit.detect_dsp()
            self.assertIsNotNone(result)
        
        self.assertEqual(mock_detect.call_count, 5)


if __name__ == '__main__':
    unittest.main()
