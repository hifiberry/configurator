#!/usr/bin/env python3
"""
HiFiBerry Configuration File Parser

Handles loading and parsing of the main configuration file for the HiFiBerry
Configuration Server.
"""

import os
import glob
import json
import logging
from typing import Dict, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)

CONFIG_FILE = "/etc/configserver/configserver.json"
CONFIG_DROP_IN_DIR = "/etc/configserver/conf.d"

class ConfigParser:
    """Parser for the HiFiBerry Configuration Server config file"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize the config parser
        
        Args:
            config_file: Path to config file (defaults to /etc/configserver/configserver.json)
        """
        self.config_file = config_file or CONFIG_FILE
        self._config = None
    
    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-merge override into base. Dict values are merged recursively,
        other types are replaced by the override value."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigParser._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _load_drop_ins(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load and merge drop-in config files from conf.d/ directory."""
        drop_in_dir = os.path.join(os.path.dirname(self.config_file), "conf.d")
        if not os.path.isdir(drop_in_dir):
            return config

        for path in sorted(glob.glob(os.path.join(drop_in_dir, "*.json"))):
            try:
                with open(path, 'r') as f:
                    snippet = json.load(f)
                if isinstance(snippet, dict):
                    self._deep_merge(config, snippet)
                    logger.debug(f"Merged drop-in config: {path}")
                else:
                    logger.warning(f"Skipping drop-in {path}: top-level value must be an object")
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid JSON in drop-in {path}: {e}")
            except Exception as e:
                logger.warning(f"Error loading drop-in {path}: {e}")

        return config

    def load_config(self) -> Dict[str, Any]:
        """
        Load the main configuration file and merge any drop-in files
        from the conf.d/ directory next to it.

        Returns:
            Dictionary containing the merged configuration data
        """
        try:
            # Load the config file (should be created by debian postinstall)
            if not os.path.exists(self.config_file):
                logger.error(f"Config file {self.config_file} not found. Please ensure package is properly installed.")
                return {}

            with open(self.config_file, 'r') as f:
                config = json.load(f)

            logger.debug(f"Loaded config from {self.config_file}: {config}")

            # Merge drop-in configs
            config = self._load_drop_ins(config)

            self._config = config
            return config

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {self.config_file}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading config file {self.config_file}: {e}")
            return {}
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the loaded configuration, loading it if necessary
        
        Returns:
            Dictionary containing the configuration data
        """
        if self._config is None:
            self._config = self.load_config()
        return self._config
    
    def get_section(self, section: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get a specific section from the configuration
        
        Args:
            section: Name of the section to retrieve
            default: Default value if section doesn't exist
            
        Returns:
            Dictionary containing the section data
        """
        config = self.get_config()
        return config.get(section, default or {})
    
    def reload_config(self) -> Dict[str, Any]:
        """
        Force reload the configuration file
        
        Returns:
            Dictionary containing the configuration data
        """
        self._config = None
        return self.load_config()
    
    def has_section(self, section: str) -> bool:
        """
        Check if a section exists in the configuration
        
        Args:
            section: Name of the section to check
            
        Returns:
            True if section exists, False otherwise
        """
        config = self.get_config()
        return section in config
    
    def get_config_file_path(self) -> str:
        """
        Get the path to the configuration file
        
        Returns:
            Path to the configuration file
        """
        return self.config_file

# Global config parser instance
_config_parser = None

def get_config_parser() -> ConfigParser:
    """
    Get the global configuration parser instance
    
    Returns:
        ConfigParser instance
    """
    global _config_parser
    if _config_parser is None:
        _config_parser = ConfigParser()
    return _config_parser

def get_config() -> Dict[str, Any]:
    """
    Get the current configuration
    
    Returns:
        Dictionary containing the configuration data
    """
    return get_config_parser().get_config()

def get_config_section(section: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get a specific section from the configuration
    
    Args:
        section: Name of the section to retrieve
        default: Default value if section doesn't exist
        
    Returns:
        Dictionary containing the section data
    """
    return get_config_parser().get_section(section, default)

def reload_config() -> Dict[str, Any]:
    """
    Force reload the configuration file
    
    Returns:
        Dictionary containing the configuration data
    """
    return get_config_parser().reload_config()
