#!/usr/bin/env python3
"""
Regression tests for config_parser module

Tests the ConfigParser class and related functions for:
- Configuration file loading and parsing
- Drop-in configuration merging
- Deep merge functionality
- Section access and validation
- Lazy loading and caching
- Error handling and edge cases
"""

import os
import tempfile
import json
from unittest.mock import patch, MagicMock
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config_parser import (
    ConfigParser,
    get_config_parser,
    get_config,
    get_config_section,
    reload_config
)


class TestConfigParserInit:
    """Test ConfigParser initialization"""

    def test_init_with_default_config_file(self):
        """Test initialization with default config file path"""
        parser = ConfigParser()
        assert parser.config_file == "/etc/configserver/configserver.json"
        assert parser._config is None

    def test_init_with_custom_config_file(self):
        """Test initialization with custom config file path"""
        custom_path = "/custom/path/config.json"
        parser = ConfigParser(config_file=custom_path)
        assert parser.config_file == custom_path
        assert parser._config is None


class TestDeepMerge:
    """Test ConfigParser._deep_merge static method"""

    def test_deep_merge_simple_values(self):
        """Test merging simple non-dict values"""
        base = {"key": "old_value"}
        override = {"key": "new_value"}
        result = ConfigParser._deep_merge(base, override)
        assert result["key"] == "new_value"

    def test_deep_merge_nested_dicts(self):
        """Test merging nested dictionaries recursively"""
        base = {"section": {"key1": "value1", "key2": "value2"}}
        override = {"section": {"key2": "updated_value2"}}
        result = ConfigParser._deep_merge(base, override)
        assert result["section"]["key1"] == "value1"
        assert result["section"]["key2"] == "updated_value2"

    def test_deep_merge_new_keys(self):
        """Test that new keys are added during merge"""
        base = {"key1": "value1"}
        override = {"key2": "value2"}
        result = ConfigParser._deep_merge(base, override)
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_deep_merge_replaces_dict_with_non_dict(self):
        """Test that dict values are replaced by non-dict values"""
        base = {"key": {"nested": "value"}}
        override = {"key": "simple_value"}
        result = ConfigParser._deep_merge(base, override)
        assert result["key"] == "simple_value"

    def test_deep_merge_replaces_non_dict_with_dict(self):
        """Test that non-dict values are replaced by dict values"""
        base = {"key": "simple_value"}
        override = {"key": {"nested": "value"}}
        result = ConfigParser._deep_merge(base, override)
        assert result["key"] == {"nested": "value"}

    def test_deep_merge_multiple_levels(self):
        """Test deep merge with multiple nesting levels"""
        base = {
            "level1": {
                "level2": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
        }
        override = {
            "level1": {
                "level2": {
                    "key2": "updated_value2"
                }
            }
        }
        result = ConfigParser._deep_merge(base, override)
        assert result["level1"]["level2"]["key1"] == "value1"
        assert result["level1"]["level2"]["key2"] == "updated_value2"

    def test_deep_merge_empty_override(self):
        """Test merge with empty override dict"""
        base = {"key": "value"}
        override = {}
        result = ConfigParser._deep_merge(base, override)
        assert result == {"key": "value"}

    def test_deep_merge_empty_base(self):
        """Test merge with empty base dict"""
        base = {}
        override = {"key": "value"}
        result = ConfigParser._deep_merge(base, override)
        assert result == {"key": "value"}


class TestLoadConfig:
    """Test ConfigParser.load_config method"""

    def test_load_config_missing_file(self):
        """Test loading config when file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "nonexistent.json")
            parser = ConfigParser(config_file=config_path)
            result = parser.load_config()
            assert result == {}

    def test_load_config_valid_json(self):
        """Test loading config from valid JSON file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}, "section2": {"key2": "value2"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.load_config()
            assert result == test_config
        finally:
            os.unlink(temp_path)

    def test_load_config_invalid_json(self):
        """Test loading config from invalid JSON file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json}")
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.load_config()
            assert result == {}
        finally:
            os.unlink(temp_path)

    def test_load_config_empty_file(self):
        """Test loading config from empty JSON file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{}")
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.load_config()
            assert result == {}
        finally:
            os.unlink(temp_path)

    def test_load_config_caches_result(self):
        """Test that load_config caches the result internally"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"key": "value"}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result1 = parser.load_config()
            # Modify the cached result
            result1["new_key"] = "new_value"
            # Check that _config was updated
            assert parser._config["new_key"] == "new_value"
        finally:
            os.unlink(temp_path)


class TestLoadDropIns:
    """Test ConfigParser._load_drop_ins method"""

    def test_load_drop_ins_no_directory(self):
        """Test loading drop-ins when conf.d directory doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            # Create config file but not conf.d directory
            with open(config_path, 'w') as f:
                json.dump({"key": "value"}, f)
            
            parser = ConfigParser(config_file=config_path)
            config = {"key": "value"}
            result = parser._load_drop_ins(config)
            assert result == {"key": "value"}

    def test_load_drop_ins_with_single_file(self):
        """Test loading drop-ins with single drop-in file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"section1": {"key1": "value1"}}, f)
            
            # Create conf.d directory and drop-in file
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            drop_in_path = os.path.join(conf_d_dir, "01-override.json")
            with open(drop_in_path, 'w') as f:
                json.dump({"section1": {"key1": "overridden"}}, f)
            
            parser = ConfigParser(config_file=config_path)
            config = {"section1": {"key1": "value1"}}
            result = parser._load_drop_ins(config)
            assert result["section1"]["key1"] == "overridden"

    def test_load_drop_ins_with_multiple_files(self):
        """Test loading drop-ins with multiple drop-in files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"key": "base"}, f)
            
            # Create conf.d directory and multiple drop-in files
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            
            # Create files that will be sorted
            drop_in_1 = os.path.join(conf_d_dir, "01-first.json")
            with open(drop_in_1, 'w') as f:
                json.dump({"key": "first"}, f)
            
            drop_in_2 = os.path.join(conf_d_dir, "02-second.json")
            with open(drop_in_2, 'w') as f:
                json.dump({"key": "second"}, f)
            
            parser = ConfigParser(config_file=config_path)
            config = {"key": "base"}
            result = parser._load_drop_ins(config)
            # Second file should override first
            assert result["key"] == "second"

    def test_load_drop_ins_invalid_json(self):
        """Test loading drop-ins with invalid JSON file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"key": "value"}, f)
            
            # Create conf.d directory with invalid JSON
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            drop_in_path = os.path.join(conf_d_dir, "bad.json")
            with open(drop_in_path, 'w') as f:
                f.write("{invalid}")
            
            parser = ConfigParser(config_file=config_path)
            config = {"key": "value"}
            result = parser._load_drop_ins(config)
            # Original config should be unchanged
            assert result == {"key": "value"}

    def test_load_drop_ins_non_dict_top_level(self):
        """Test loading drop-ins with non-dict top-level value"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"key": "value"}, f)
            
            # Create conf.d directory with array as top-level
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            drop_in_path = os.path.join(conf_d_dir, "array.json")
            with open(drop_in_path, 'w') as f:
                json.dump(["item1", "item2"], f)
            
            parser = ConfigParser(config_file=config_path)
            config = {"key": "value"}
            result = parser._load_drop_ins(config)
            # Original config should be unchanged
            assert result == {"key": "value"}

    def test_load_drop_ins_sorted_order(self):
        """Test that drop-in files are loaded in sorted order"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"order": []}, f)
            
            # Create conf.d directory with unsorted files
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            
            # Create files in reverse order
            drop_in_3 = os.path.join(conf_d_dir, "03-third.json")
            with open(drop_in_3, 'w') as f:
                json.dump({"order": [3]}, f)
            
            drop_in_1 = os.path.join(conf_d_dir, "01-first.json")
            with open(drop_in_1, 'w') as f:
                json.dump({"order": [1]}, f)
            
            drop_in_2 = os.path.join(conf_d_dir, "02-second.json")
            with open(drop_in_2, 'w') as f:
                json.dump({"order": [2]}, f)
            
            parser = ConfigParser(config_file=config_path)
            config = {"order": []}
            result = parser._load_drop_ins(config)
            # Last file in sorted order wins in merge (03-third.json)
            assert result["order"] == [3]


class TestGetConfig:
    """Test ConfigParser.get_config method"""

    def test_get_config_lazy_loads(self):
        """Test that get_config lazily loads the config"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"key": "value"}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            assert parser._config is None  # Not loaded yet
            result = parser.get_config()
            assert parser._config is not None  # Now loaded
            assert result == test_config
        finally:
            os.unlink(temp_path)

    def test_get_config_returns_cached_value(self):
        """Test that get_config returns cached value on subsequent calls"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"key": "value"}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result1 = parser.get_config()
            result2 = parser.get_config()
            # Both should be the same object
            assert result1 is result2
        finally:
            os.unlink(temp_path)


class TestGetSection:
    """Test ConfigParser.get_section method"""

    def test_get_section_exists(self):
        """Test getting a section that exists"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}, "section2": {"key2": "value2"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.get_section("section1")
            assert result == {"key": "value"}
        finally:
            os.unlink(temp_path)

    def test_get_section_not_exists_default_none(self):
        """Test getting a section that doesn't exist with no default"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.get_section("nonexistent")
            assert result == {}
        finally:
            os.unlink(temp_path)

    def test_get_section_not_exists_with_default(self):
        """Test getting a section that doesn't exist with default value"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            default = {"default_key": "default_value"}
            result = parser.get_section("nonexistent", default)
            assert result == default
        finally:
            os.unlink(temp_path)


class TestReloadConfig:
    """Test ConfigParser.reload_config method"""

    def test_reload_config_clears_cache(self):
        """Test that reload_config clears the cached config"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"key": "value"}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            # Load config
            config1 = parser.get_config()
            assert parser._config is not None
            # Reload config
            config2 = parser.reload_config()
            # Should be different objects
            assert config1 is not config2
            assert config1 == config2
        finally:
            os.unlink(temp_path)

    def test_reload_config_reflects_file_changes(self):
        """Test that reload_config reflects changes to config file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "original"}, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            config1 = parser.get_config()
            assert config1["key"] == "original"
            
            # Modify file
            with open(temp_path, 'w') as f:
                json.dump({"key": "modified"}, f)
            
            # Reload
            config2 = parser.reload_config()
            assert config2["key"] == "modified"
        finally:
            os.unlink(temp_path)


class TestHasSection:
    """Test ConfigParser.has_section method"""

    def test_has_section_exists(self):
        """Test checking if section exists"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            assert parser.has_section("section1") is True
        finally:
            os.unlink(temp_path)

    def test_has_section_not_exists(self):
        """Test checking if section doesn't exist"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"section1": {"key": "value"}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            assert parser.has_section("nonexistent") is False
        finally:
            os.unlink(temp_path)


class TestGetConfigFilePath:
    """Test ConfigParser.get_config_file_path method"""

    def test_get_config_file_path_default(self):
        """Test getting default config file path"""
        parser = ConfigParser()
        assert parser.get_config_file_path() == "/etc/configserver/configserver.json"

    def test_get_config_file_path_custom(self):
        """Test getting custom config file path"""
        custom_path = "/custom/path/config.json"
        parser = ConfigParser(config_file=custom_path)
        assert parser.get_config_file_path() == custom_path


class TestGlobalFunctions:
    """Test module-level global functions"""

    def test_get_config_parser_returns_singleton(self):
        """Test that get_config_parser returns a singleton instance"""
        # Clear the global instance first
        import config_parser as cp_module
        cp_module._config_parser = None
        
        parser1 = get_config_parser()
        parser2 = get_config_parser()
        assert parser1 is parser2

    @patch('config_parser.get_config_parser')
    def test_get_config_function(self, mock_get_parser):
        """Test module-level get_config function"""
        mock_parser = MagicMock()
        mock_parser.get_config.return_value = {"test": "config"}
        mock_get_parser.return_value = mock_parser
        
        result = get_config()
        assert result == {"test": "config"}
        mock_parser.get_config.assert_called_once()

    @patch('config_parser.get_config_parser')
    def test_get_config_section_function(self, mock_get_parser):
        """Test module-level get_config_section function"""
        mock_parser = MagicMock()
        mock_parser.get_section.return_value = {"section": "data"}
        mock_get_parser.return_value = mock_parser
        
        result = get_config_section("test_section", {"default": "value"})
        assert result == {"section": "data"}
        mock_parser.get_section.assert_called_once_with("test_section", {"default": "value"})

    @patch('config_parser.get_config_parser')
    def test_reload_config_function(self, mock_get_parser):
        """Test module-level reload_config function"""
        mock_parser = MagicMock()
        mock_parser.reload_config.return_value = {"reloaded": "config"}
        mock_get_parser.return_value = mock_parser
        
        result = reload_config()
        assert result == {"reloaded": "config"}
        mock_parser.reload_config.assert_called_once()


class TestEdgeCasesAndRobustness:
    """Test edge cases and robustness"""

    def test_config_with_special_characters(self):
        """Test loading config with special characters"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "section": {
                    "key_with_underscore": "value",
                    "key-with-dash": "value",
                    "key.with.dots": "value",
                    "keyWithCamelCase": "value"
                }
            }
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.get_config()
            assert result == test_config
        finally:
            os.unlink(temp_path)

    def test_config_with_unicode(self):
        """Test loading config with unicode characters"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            test_config = {
                "section": {
                    "key": "value with émojis 🎵"
                }
            }
            json.dump(test_config, f, ensure_ascii=False)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.get_config()
            assert result["section"]["key"] == "value with émojis 🎵"
        finally:
            os.unlink(temp_path)

    def test_config_with_various_types(self):
        """Test loading config with various JSON data types"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "string": "value",
                "number": 42,
                "float": 3.14,
                "boolean": True,
                "null": None,
                "array": [1, 2, 3],
                "nested": {
                    "deep": {
                        "value": "test"
                    }
                }
            }
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            parser = ConfigParser(config_file=temp_path)
            result = parser.get_config()
            assert result == test_config
        finally:
            os.unlink(temp_path)

    def test_drop_in_with_new_sections(self):
        """Test drop-in that adds completely new sections"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({"section1": {"key1": "value1"}}, f)
            
            # Create conf.d directory with new section
            conf_d_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d_dir)
            drop_in_path = os.path.join(conf_d_dir, "new.json")
            with open(drop_in_path, 'w') as f:
                json.dump({"section2": {"key2": "value2"}}, f)
            
            parser = ConfigParser(config_file=config_path)
            config = parser.load_config()
            assert "section1" in config
            assert "section2" in config
            assert config["section1"]["key1"] == "value1"
            assert config["section2"]["key2"] == "value2"
