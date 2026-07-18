#!/usr/bin/env python3
"""
Regression tests for asoundconf module

Tests the ALSAConfig class and related functions for:
- Configuration creation and validation
- Checksum calculation and change detection
- File I/O operations
- Argument parsing
- Type consistency
"""

import os
import tempfile
import hashlib
import pytest
from unittest.mock import patch, MagicMock
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from asoundconf import ALSAConfig, SIMPLE_CONFIG_TEMPLATE, parse_arguments, main


class TestALSAConfig:
    """Test cases for ALSAConfig class"""
    
    def test_init_creates_instance(self):
        """Test that ALSAConfig initializes correctly with default parameters"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            config = ALSAConfig(filename=temp_path)
            assert config.filename == temp_path
            assert config.config == ""
            assert isinstance(config.original_checksum, str)
            assert len(config.original_checksum) == 32  # MD5 hash length
        finally:
            os.unlink(temp_path)
    
    def test_load_config_from_existing_file(self, temp_config_file):
        """Test loading configuration from an existing file"""
        test_content = "test configuration"
        with open(temp_config_file, 'w') as f:
            f.write(test_content)
        
        config = ALSAConfig(filename=temp_config_file)
        assert config.config == test_content
    
    def test_load_config_from_nonexistent_file(self, temp_config_file):
        """Test loading configuration when file doesn't exist"""
        os.unlink(temp_config_file)  # Remove the file
        
        config = ALSAConfig(filename=temp_config_file)
        assert config.config == ""
        assert len(config.original_checksum) == 32  # MD5 hash of empty string
    
    def test_calculate_checksum(self, temp_config_file):
        """Test checksum calculation consistency"""
        config = ALSAConfig(filename=temp_config_file)
        
        test_content = "test configuration"
        config.config = test_content
        
        expected_checksum = hashlib.md5(test_content.encode('utf-8')).hexdigest()
        calculated_checksum = config.calculate_checksum()
        
        assert calculated_checksum == expected_checksum
        assert len(calculated_checksum) == 32
    
    def test_checksum_changes_with_config(self, temp_config_file):
        """Test that checksum changes when configuration changes"""
        config = ALSAConfig(filename=temp_config_file)
        
        checksum1 = config.calculate_checksum()
        config.config = "new content"
        checksum2 = config.calculate_checksum()
        
        assert checksum1 != checksum2
    
    def test_create_simple_config(self, temp_config_file):
        """Test simple configuration creation"""
        config = ALSAConfig(filename=temp_config_file)
        
        hw = 1
        channels = 6
        config.create_simple_config(hw=hw, channels=channels)
        
        assert str(hw) in config.config
        assert str(channels) in config.config
        assert "type hw" in config.config
        assert "card 1" in config.config
        assert "channels 6" in config.config
    
    def test_create_simple_config_format(self, temp_config_file):
        """Test that simple config has correct format structure"""
        config = ALSAConfig(filename=temp_config_file)
        config.create_simple_config(hw=0, channels=2)
        
        # Verify key sections are present
        assert "pcm.!default" in config.config
        assert "ctl.!default" in config.config
        assert "device 0" in config.config
        assert "type hw" in config.config
    
    def test_create_simple_config_different_values(self, temp_config_file):
        """Test config creation with various hardware card and channel values"""
        config = ALSAConfig(filename=temp_config_file)
        
        test_cases = [
            (0, 2),
            (5, 8),
            (10, 4),
        ]
        
        for hw, channels in test_cases:
            config.create_simple_config(hw=hw, channels=channels)
            assert f"card {hw}" in config.config
            assert f"channels {channels}" in config.config
    
    def test_save_with_changes(self, temp_config_file):
        """Test that save returns True when configuration changes"""
        config = ALSAConfig(filename=temp_config_file)
        
        config.create_simple_config(hw=1, channels=2)
        result = config.save()
        
        assert result is True
    
    def test_save_without_changes(self, temp_config_file):
        """Test that save returns False when configuration hasn't changed"""
        config = ALSAConfig(filename=temp_config_file)
        
        # No changes made
        result = config.save()
        
        assert result is False
    
    def test_save_creates_file(self, temp_config_file):
        """Test that save creates the file if it doesn't exist"""
        if os.path.exists(temp_config_file):
            os.unlink(temp_config_file)
        
        config = ALSAConfig(filename=temp_config_file)
        config.create_simple_config(hw=0, channels=2)
        config.save()
        
        assert os.path.exists(temp_config_file)
    
    def test_save_persists_content(self, temp_config_file):
        """Test that saved configuration can be reloaded"""
        config1 = ALSAConfig(filename=temp_config_file)
        config1.create_simple_config(hw=2, channels=4)
        config1.save()
        
        # Load with new instance
        config2 = ALSAConfig(filename=temp_config_file)
        
        assert config2.config == config1.config
        assert "card 2" in config2.config
        assert "channels 4" in config2.config
    
    def test_save_updates_original_checksum(self, temp_config_file):
        """Test that save updates the original_checksum after writing"""
        config = ALSAConfig(filename=temp_config_file)
        original_checksum = config.original_checksum
        
        config.create_simple_config(hw=1, channels=2)
        config.save()
        
        assert config.original_checksum != original_checksum
        assert config.original_checksum == config.calculate_checksum()
    
    def test_multiple_saves(self, temp_config_file):
        """Test multiple save operations with different configurations"""
        config = ALSAConfig(filename=temp_config_file)
        
        # First save
        config.create_simple_config(hw=0, channels=2)
        assert config.save() is True
        
        # Second save without changes
        assert config.save() is False
        
        # Change and save again
        config.create_simple_config(hw=1, channels=4)
        assert config.save() is True
        
        # Verify final content
        assert "card 1" in config.config
        assert "channels 4" in config.config
    
    def test_config_type_consistency(self, temp_config_file):
        """Test that all instance attributes maintain consistent types"""
        config = ALSAConfig(filename=temp_config_file)
        
        assert isinstance(config.filename, str)
        assert isinstance(config.config, str)
        assert isinstance(config.original_checksum, str)
        
        config.create_simple_config(hw=0, channels=2)
        
        assert isinstance(config.filename, str)
        assert isinstance(config.config, str)
        assert isinstance(config.original_checksum, str)


class TestParseArguments:
    """Test cases for argument parsing"""
    
    def test_parse_arguments_default_values(self):
        """Test default argument values"""
        with patch('sys.argv', ['asoundconf.py']):
            args = parse_arguments()
            assert args.default is False
            assert args.channels == 2
            assert args.hw == 0
    
    def test_parse_arguments_with_defaults_flag(self):
        """Test parsing with --default flag"""
        with patch('sys.argv', ['asoundconf.py', '--default']):
            args = parse_arguments()
            assert args.default is True
    
    def test_parse_arguments_with_hw(self):
        """Test parsing with --hw argument"""
        with patch('sys.argv', ['asoundconf.py', '--hw', '5']):
            args = parse_arguments()
            assert args.hw == 5
    
    def test_parse_arguments_with_channels(self):
        """Test parsing with --channels argument"""
        with patch('sys.argv', ['asoundconf.py', '--channels', '8']):
            args = parse_arguments()
            assert args.channels == 8
    
    def test_parse_arguments_combined(self):
        """Test parsing with multiple arguments"""
        with patch('sys.argv', ['asoundconf.py', '--default', '--hw', '3', '--channels', '6']):
            args = parse_arguments()
            assert args.default is True
            assert args.hw == 3
            assert args.channels == 6
    
    def test_parse_arguments_returns_namespace(self):
        """Test that parse_arguments returns argparse.Namespace"""
        with patch('sys.argv', ['asoundconf.py']):
            args = parse_arguments()
            assert hasattr(args, 'default')
            assert hasattr(args, 'hw')
            assert hasattr(args, 'channels')


class TestMain:
    """Test cases for main function"""
    
    def test_main_with_default_flag(self):
        """Test main function execution with --default flag"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            with patch('sys.argv', ['asoundconf.py', '--default', '--hw', '0', '--channels', '2']):
                with patch('asoundconf.ALSAConfig') as mock_config:
                    mock_instance = MagicMock()
                    mock_instance.save.return_value = True
                    mock_config.return_value = mock_instance
                    
                    with patch('builtins.print') as mock_print:
                        main()
                    
                    mock_instance.create_simple_config.assert_called_once_with(hw=0, channels=2)
                    mock_instance.save.assert_called_once()
                    mock_print.assert_called_with("Configuration saved.")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_main_without_default_flag(self):
        """Test main function without --default flag"""
        with patch('sys.argv', ['asoundconf.py']):
            with patch('asoundconf.ALSAConfig') as mock_config:
                mock_instance = MagicMock()
                mock_config.return_value = mock_instance
                
                with patch('builtins.print') as mock_print:
                    main()
                
                mock_instance.create_simple_config.assert_not_called()
                mock_instance.save.assert_not_called()
                mock_print.assert_called_with("No --default flag provided, no configuration created.")
    
    def test_main_no_changes_to_save(self):
        """Test main function when no changes to save"""
        with patch('sys.argv', ['asoundconf.py', '--default']):
            with patch('asoundconf.ALSAConfig') as mock_config:
                mock_instance = MagicMock()
                mock_instance.save.return_value = False
                mock_config.return_value = mock_instance
                
                with patch('builtins.print') as mock_print:
                    main()
                
                mock_print.assert_called_with("No changes to save.")


class TestTemplateFormat:
    """Test cases for configuration template"""
    
    def test_template_has_placeholder_for_hw(self):
        """Test that template contains hw placeholder"""
        assert "{hw}" in SIMPLE_CONFIG_TEMPLATE
    
    def test_template_has_placeholder_for_channels(self):
        """Test that template contains channels placeholder"""
        assert "{channels}" in SIMPLE_CONFIG_TEMPLATE
    
    def test_template_format_succeeds(self):
        """Test that template formatting works correctly"""
        result = SIMPLE_CONFIG_TEMPLATE.format(hw=0, channels=2)
        assert "card 0" in result
        assert "channels 2" in result
        # Check that format placeholders were replaced (not that { is absent, since it's in ALSA syntax)
        assert "{hw}" not in result
        assert "{channels}" not in result
    
    def test_template_structure(self):
        """Test that template contains required sections"""
        assert "pcm.!default" in SIMPLE_CONFIG_TEMPLATE
        assert "ctl.!default" in SIMPLE_CONFIG_TEMPLATE
        assert "type hw" in SIMPLE_CONFIG_TEMPLATE
        assert "device 0" in SIMPLE_CONFIG_TEMPLATE


class TestIntegration:
    """Integration tests combining multiple components"""
    
    def test_full_workflow_create_and_save(self):
        """Test complete workflow: create config and save to file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            # Create and configure
            config = ALSAConfig(filename=temp_path)
            config.create_simple_config(hw=3, channels=8)
            saved = config.save()
            
            assert saved is True
            assert os.path.exists(temp_path)
            
            # Verify persistence
            with open(temp_path, 'r') as f:
                content = f.read()
            
            assert "card 3" in content
            assert "channels 8" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_full_workflow_load_and_modify(self):
        """Test loading existing config and modifying it"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("existing configuration")
            temp_path = f.name
        
        try:
            config = ALSAConfig(filename=temp_path)
            assert config.config == "existing configuration"
            
            # Modify
            config.create_simple_config(hw=1, channels=2)
            assert config.save() is True
            
            # Reload and verify
            config2 = ALSAConfig(filename=temp_path)
            assert "card 1" in config2.config
            assert "channels 2" in config2.config
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_checksum_tracking_throughout_workflow(self):
        """Test that checksums are correctly tracked through full workflow"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            # Initial load
            config = ALSAConfig(filename=temp_path)
            checksum1 = config.original_checksum
            
            # Create config
            config.create_simple_config(hw=0, channels=2)
            checksum2_should_differ = config.calculate_checksum()
            
            assert checksum1 != checksum2_should_differ
            assert config.original_checksum == checksum1  # Not updated yet
            
            # Save
            config.save()
            
            assert config.original_checksum == checksum2_should_differ
            
            # Load in new instance
            config2 = ALSAConfig(filename=temp_path)
            assert config2.original_checksum == config.original_checksum
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
