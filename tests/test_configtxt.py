#!/usr/bin/env python3
"""
Regression tests for ConfigTxt module

Tests cover:
- File initialization and persistence
- Sound card configuration (onboard, HDMI)
- EEPROM settings
- Interface configuration (I2C, SPI)
- Device tree overlays
- Configuration change tracking
- Edge cases and error handling
"""

import unittest
import tempfile
import os
import sys
import shutil
from unittest.mock import MagicMock

# Mock soundcard module BEFORE any imports
sys.modules['soundcard'] = MagicMock()

# Add parent directory to path so we can import src as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Now import ConfigTxt from the src package
from src.configtxt import ConfigTxt  # noqa: E402


class TestConfigTxtInitialization(unittest.TestCase):
    """Test ConfigTxt initialization and file handling"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        # Create a minimal config file
        with open(self.config_path, 'w') as f:
            f.write("# Test config file\n")
            f.write("dtparam=audio=on\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_initialization_with_existing_file(self):
        """Test initializing ConfigTxt with an existing file"""
        config = ConfigTxt(self.config_path)
        self.assertTrue(len(config.lines) > 0)
        self.assertIsNotNone(config.original_checksum)

    def test_initialization_with_nonexistent_file_raises_error(self):
        """Test that initializing with a non-existent file raises FileNotFoundError"""
        nonexistent_path = os.path.join(self.temp_dir, 'nonexistent.txt')
        with self.assertRaises(FileNotFoundError):
            ConfigTxt(nonexistent_path)

    def test_original_checksum_computed(self):
        """Test that original checksum is computed on initialization"""
        config = ConfigTxt(self.config_path)
        self.assertIsNotNone(config.original_checksum)
        self.assertEqual(len(config.original_checksum), 64)  # SHA256 hex digest


class TestDetectionToggle(unittest.TestCase):
    """Test HiFiBerry detection enable/disable"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_detection_disabled_not_initially_disabled(self):
        """Test that detection is not disabled by default"""
        config = ConfigTxt(self.config_path)
        self.assertFalse(config.is_detection_disabled())

    def test_disable_detection_adds_comment(self):
        """Test that disabling detection adds the disabled comment"""
        config = ConfigTxt(self.config_path)
        config.disable_detection()
        self.assertTrue(config.is_detection_disabled())

    def test_enable_detection_removes_comment(self):
        """Test that enabling detection removes the disabled comment"""
        config = ConfigTxt(self.config_path)
        config.disable_detection()
        self.assertTrue(config.is_detection_disabled())
        config.enable_detection()
        self.assertFalse(config.is_detection_disabled())

    def test_disable_detection_idempotent(self):
        """Test that disabling detection multiple times is idempotent"""
        config = ConfigTxt(self.config_path)
        original_length = len(config.lines)
        config.disable_detection()
        config.disable_detection()
        config.disable_detection()
        # Should only have added one line
        self.assertEqual(len(config.lines), original_length + 1)

    def test_enable_detection_idempotent(self):
        """Test that enabling detection multiple times is idempotent"""
        config = ConfigTxt(self.config_path)
        config.disable_detection()
        length_after_disable = len(config.lines)
        config.enable_detection()
        config.enable_detection()
        # Should still be at the same length
        self.assertEqual(len(config.lines), length_after_disable - 1)


class TestSoundCardConfiguration(unittest.TestCase):
    """Test sound card configuration methods"""

    def setUp(self):
        """Create a temporary config file with sound settings"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
            f.write("dtparam=audio=on\n")
            f.write("dtoverlay=vc4-kms-v3d\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_disable_onboard_sound(self):
        """Test disabling onboard sound"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        
        # Find the audio param line
        audio_lines = [line for line in config.lines if 'dtparam=audio=' in line]
        self.assertTrue(any('off' in line for line in audio_lines))

    def test_enable_onboard_sound(self):
        """Test enabling onboard sound"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.enable_onboard_sound()
        
        audio_lines = [line for line in config.lines if 'dtparam=audio=' in line]
        self.assertTrue(any('on' in line for line in audio_lines))

    def test_disable_hdmi_sound(self):
        """Test disabling HDMI sound"""
        config = ConfigTxt(self.config_path)
        config.disable_hdmi_sound()
        
        # Check that noaudio was added
        hdmi_lines = [line for line in config.lines if 'dtoverlay=vc4-kms-v3d' in line]
        self.assertTrue(any('noaudio' in line for line in hdmi_lines))

    def test_enable_hdmi_sound(self):
        """Test enabling HDMI sound"""
        config = ConfigTxt(self.config_path)
        config.disable_hdmi_sound()
        config.enable_hdmi_sound()
        
        # Check that noaudio was removed
        hdmi_lines = [line for line in config.lines if 'dtoverlay=vc4-kms-v3d' in line]
        self.assertFalse(any('noaudio' in line for line in hdmi_lines))

    def test_disable_hdmi_without_existing_overlay(self):
        """Test disabling HDMI sound when vc4-kms-v3d overlay doesn't exist"""
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
        
        config = ConfigTxt(self.config_path)
        initial_length = len(config.lines)
        config.disable_hdmi_sound()
        # Should not add a line if overlay doesn't exist
        self.assertEqual(len(config.lines), initial_length)


class TestEEPROMConfiguration(unittest.TestCase):
    """Test EEPROM configuration"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_disable_eeprom(self):
        """Test disabling EEPROM read"""
        config = ConfigTxt(self.config_path)
        config.disable_eeprom()
        
        eeprom_lines = [line for line in config.lines if 'force_eeprom_read=' in line]
        self.assertTrue(any('0' in line for line in eeprom_lines))

    def test_enable_eeprom(self):
        """Test enabling EEPROM read"""
        config = ConfigTxt(self.config_path)
        config.disable_eeprom()
        config.enable_eeprom()
        
        eeprom_lines = [line for line in config.lines if 'force_eeprom_read=' in line]
        self.assertTrue(any('1' in line for line in eeprom_lines))


class TestInterfaceConfiguration(unittest.TestCase):
    """Test I2C and SPI interface configuration"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_enable_i2c(self):
        """Test enabling I2C interface"""
        config = ConfigTxt(self.config_path)
        config.enable_i2c()
        
        i2c_lines = [line for line in config.lines if 'dtparam=i2c_arm=' in line]
        self.assertTrue(any('on' in line for line in i2c_lines))

    def test_disable_i2c(self):
        """Test disabling I2C interface"""
        config = ConfigTxt(self.config_path)
        config.enable_i2c()
        config.disable_i2c()
        
        i2c_lines = [line for line in config.lines if 'dtparam=i2c_arm=' in line]
        self.assertTrue(any('off' in line for line in i2c_lines))

    def test_enable_spi(self):
        """Test enabling SPI interface"""
        config = ConfigTxt(self.config_path)
        config.enable_spi()
        
        spi_lines = [line for line in config.lines if 'dtparam=spi=' in line]
        self.assertTrue(any('on' in line for line in spi_lines))

    def test_disable_spi(self):
        """Test disabling SPI interface"""
        config = ConfigTxt(self.config_path)
        config.enable_spi()
        config.disable_spi()
        
        spi_lines = [line for line in config.lines if 'dtparam=spi=' in line]
        self.assertTrue(any('off' in line for line in spi_lines))


class TestOverlayManagement(unittest.TestCase):
    """Test overlay enable/disable and removal"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
            f.write("dtoverlay=hifiberry-dac\n")
            f.write("# HiFiBerry card: HiFiBerry DAC\n")
            f.write("force_eeprom_read=0\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_enable_overlay_adds_line(self):
        """Test that enable_overlay adds a new overlay line"""
        config = ConfigTxt(self.config_path)
        config.enable_overlay("hifiberry-amp")
        
        overlay_lines = [line for line in config.lines if 'dtoverlay=hifiberry-amp' in line]
        self.assertEqual(len(overlay_lines), 1)

    def test_enable_overlay_with_card_name_comment(self):
        """Test enable_overlay adds a card name comment"""
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_overlay("hifiberry-dac", card_name="HiFiBerry DAC")
        
        card_comment_lines = [line for line in config.lines if 'HiFiBerry card:' in line]
        self.assertTrue(len(card_comment_lines) > 0)

    def test_enable_overlay_with_disable_eeprom(self):
        """Test enable_overlay can disable EEPROM"""
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_overlay("hifiberry-dac", disable_eeprom=True)
        
        eeprom_lines = [line for line in config.lines if 'force_eeprom_read=0' in line]
        self.assertTrue(len(eeprom_lines) > 0)

    def test_remove_hifiberry_overlays(self):
        """Test removing all HiFiBerry overlays"""
        config = ConfigTxt(self.config_path)
        config.remove_hifiberry_overlays()
        
        # Verify HiFiBerry overlay is removed
        overlay_lines = [line for line in config.lines if 'dtoverlay=hifiberry' in line]
        self.assertEqual(len(overlay_lines), 0)
        
        # Verify card comment is removed
        card_comment_lines = [line for line in config.lines if 'HiFiBerry card:' in line]
        self.assertEqual(len(card_comment_lines), 0)
        
        # Verify force_eeprom_read is removed
        eeprom_lines = [line for line in config.lines if 'force_eeprom_read=' in line]
        self.assertEqual(len(eeprom_lines), 0)

    def test_enable_hat_i2c(self):
        """Test enabling HAT I2C overlay"""
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_hat_i2c()
        
        hat_i2c_lines = [line for line in config.lines if 'i2c-gpio' in line]
        self.assertTrue(len(hat_i2c_lines) > 0)

    def test_enable_hat_i2c_no_duplicates(self):
        """Test that enabling HAT I2C twice doesn't create duplicates"""
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_hat_i2c()
        config.enable_hat_i2c()
        
        hat_i2c_lines = [line for line in config.lines if 'i2c-gpio' in line]
        self.assertEqual(len(hat_i2c_lines), 1)

    def test_disable_hat_i2c(self):
        """Test disabling HAT I2C overlay"""
        config = ConfigTxt(self.config_path)
        config.enable_hat_i2c()
        config.disable_hat_i2c()
        
        hat_i2c_lines = [line for line in config.lines if 'i2c-gpio' in line]
        self.assertEqual(len(hat_i2c_lines), 0)


class TestUPDIConfiguration(unittest.TestCase):
    """Test UPDI (UART) configuration"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_enable_updi(self):
        """Test enabling UPDI configuration"""
        config = ConfigTxt(self.config_path)
        config.enable_updi()
        
        # Check for required lines
        lines_text = "".join(config.lines)
        self.assertIn("enable_uart=1", lines_text)
        self.assertIn("dtoverlay=uart0", lines_text)
        self.assertIn("dtoverlay=disable-bt", lines_text)

    def test_enable_updi_idempotent(self):
        """Test that enabling UPDI multiple times is idempotent"""
        config = ConfigTxt(self.config_path)
        config.enable_updi()
        length_after_first = len(config.lines)
        config.enable_updi()
        # Should not add duplicate lines
        self.assertEqual(len(config.lines), length_after_first)


class TestChangeTracking(unittest.TestCase):
    """Test change detection and persistence"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
            f.write("dtparam=audio=on\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_changes_made_false_without_modifications(self):
        """Test that changes_made is False if no modifications are made"""
        config = ConfigTxt(self.config_path)
        config.save()
        self.assertFalse(config.changes_made)

    def test_changes_made_true_with_modifications(self):
        """Test that changes_made is True after modifications"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.save()
        self.assertTrue(config.changes_made)

    def test_backup_created_on_change(self):
        """Test that a backup is created when changes are made"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.save()
        
        backup_path = self.config_path + ".backup"
        self.assertTrue(os.path.exists(backup_path))

    def test_changes_persisted_to_file(self):
        """Test that changes are persisted to the file"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.save()
        
        # Read the file again
        with open(self.config_path, 'r') as f:
            content = f.read()
        
        self.assertIn("dtparam=audio=off", content)

    def test_multiple_changes_persisted(self):
        """Test that multiple changes are all persisted"""
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.enable_i2c()
        config.enable_spi()
        config.save()
        
        # Read the file again
        with open(self.config_path, 'r') as f:
            content = f.read()
        
        self.assertIn("dtparam=audio=off", content)
        self.assertIn("dtparam=i2c_arm=on", content)
        self.assertIn("dtparam=spi=on", content)


class TestDefaultConfiguration(unittest.TestCase):
    """Test default configuration method"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')
        
        with open(self.config_path, 'w') as f:
            f.write("# Test config\n")
            f.write("dtparam=audio=on\n")
            f.write("dtoverlay=hifiberry-dac\n")

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_default_config_applies_all_settings(self):
        """Test that default_config applies all expected settings"""
        config = ConfigTxt(self.config_path)
        config.default_config()
        
        lines_text = "".join(config.lines)
        
        # Should have disabled HiFiBerry overlays
        self.assertNotIn("dtoverlay=hifiberry", lines_text)
        
        # Should have disabled onboard sound
        self.assertIn("dtparam=audio=off", lines_text)
        
        # Should have enabled SPI and I2C
        self.assertIn("dtparam=spi=on", lines_text)
        self.assertIn("dtparam=i2c_arm=on", lines_text)


class TestEdgeCasesAndRobustness(unittest.TestCase):
    """Test edge cases and unusual scenarios"""

    def setUp(self):
        """Create a temporary config file"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.txt')

    def tearDown(self):
        """Clean up temporary directory"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_empty_config_file(self):
        """Test handling of an empty config file"""
        with open(self.config_path, 'w') as f:
            f.write("")
        
        config = ConfigTxt(self.config_path)
        config.enable_i2c()
        config.save()
        
        with open(self.config_path, 'r') as f:
            content = f.read()
        
        self.assertIn("dtparam=i2c_arm=on", content)

    def test_config_with_only_comments(self):
        """Test handling of a config with only comments"""
        with open(self.config_path, 'w') as f:
            f.write("# Comment 1\n")
            f.write("# Comment 2\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_spi()
        
        spi_lines = [line for line in config.lines if 'dtparam=spi=' in line]
        self.assertTrue(len(spi_lines) > 0)

    def test_config_with_whitespace_variations(self):
        """Test handling of lines with varying whitespace"""
        with open(self.config_path, 'w') as f:
            f.write("  dtparam=audio=on  \n")
            f.write("\n")
            f.write("dtoverlay=vc4-kms-v3d\n")
        
        config = ConfigTxt(self.config_path)
        config.disable_hdmi_sound()
        
        # Should find the HDMI line despite whitespace
        hdmi_lines = [line for line in config.lines if 'dtoverlay=vc4-kms-v3d' in line]
        self.assertTrue(any('noaudio' in line for line in hdmi_lines))

    def test_multiple_occurrences_of_same_setting(self):
        """Test handling of duplicate settings (last one wins)"""
        with open(self.config_path, 'w') as f:
            f.write("dtparam=audio=on\n")
            f.write("dtparam=audio=off\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_onboard_sound()
        
        # Should update the first occurrence
        self.assertEqual(config.lines[0].strip(), "dtparam=audio=on")

    def test_very_long_config_file(self):
        """Test handling of a very large config file"""
        with open(self.config_path, 'w') as f:
            for i in range(1000):
                f.write(f"# Comment {i}\n")
        
        config = ConfigTxt(self.config_path)
        config.enable_i2c()
        
        self.assertTrue(len(config.lines) > 1000)

    def test_unicode_in_comments(self):
        """Test handling of Unicode characters in comments"""
        with open(self.config_path, 'w') as f:
            f.write("# Configuration for HiFiBerry 🎵\n")
            f.write("dtparam=audio=on\n")
        
        config = ConfigTxt(self.config_path)
        config.disable_onboard_sound()
        config.save()
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn("🎵", content)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
