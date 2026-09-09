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
import time
from typing import Dict, Any, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

CONFIG_FILE = "/etc/configserver/configserver.json"
CONFIG_DROP_IN_DIR = "/etc/configserver/conf.d"

# How long a read that failed for a reason outside the file itself is trusted
# before it is tried again. Long enough that a permanently broken system logs
# twice a minute rather than once per permission lookup, short enough that a
# device recovers on its own. See _cache_result.
TRANSIENT_RETRY_SECONDS = 30

class ConfigParser:
    """Parser for the HiFiBerry Configuration Server config file"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize the config parser
        
        Args:
            config_file: Path to config file (defaults to /etc/configserver/configserver.json)
        """
        self.config_file = config_file or CONFIG_FILE
        # (fingerprint, config, retry_at) as one tuple so it is replaced
        # atomically: two threads loading at once can then only lose a load,
        # never pair a fresh fingerprint with a stale config (see _fingerprint).
        self._cache: Optional[Tuple[Any, Dict[str, Any], Optional[float]]] = None
    
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

    def _drop_in_dir(self) -> str:
        """The conf.d directory that sits next to the main config file."""
        return os.path.join(os.path.dirname(self.config_file), "conf.d")

    def _fingerprint(self) -> Any:
        """Cheap identity of everything get_config() reads.

        A drop-in dropped into conf.d underneath a *running* config-server has
        to be seen without a restart: it is how an extension package grants the
        Web UI permission to start and stop its service, and until it is read
        the permission lookup falls back to "status", leaving the player's
        controls inert with no error to show for it. Only the extension
        installer used to refresh this, so a shell "apt install" -- or an edit
        to a permission level -- went unnoticed.

        stat rather than content: get_config() is called on every permission
        lookup, so this runs constantly and must stay cheap. The file list
        catches an added or removed drop-in whatever the timestamps do; size
        and mtime catch an edit to one.
        """
        paths = [self.config_file]
        paths += sorted(glob.glob(os.path.join(self._drop_in_dir(), "*.json")))

        stamps = []
        for path in paths:
            try:
                st = os.stat(path)
                stamps.append((path, st.st_mtime_ns, st.st_size))
            except OSError:
                stamps.append((path, None, None))
        return tuple(stamps)

    def _cache_result(self, fingerprint: Any, config: Dict[str, Any],
                      retry_at: Optional[float] = None) -> Dict[str, Any]:
        """Cache a read, including one that failed.

        An empty result is cached like any other: a missing or unparseable
        config file logs at error level, and get_config() runs on every
        permission lookup, so re-reading per call would do nothing but fill the
        journal. Keyed on the fingerprint, so a file that is later created or
        repaired -- both of which change its mtime and size -- is picked up.

        retry_at additionally expires the cache at a point in time, for a read
        that failed for a reason outside the file's own contents: an I/O error,
        fd exhaustion, an EACCES window while permissions are being fixed. Those
        clear without the file being written, so the fingerprint alone would
        never re-read, and every permission lookup would stay on its "status"
        fallback for the life of the process -- the exact symptom conf.d change
        detection exists to prevent.
        """
        self._cache = (fingerprint, config, retry_at)
        return config

    def _load_drop_ins(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load and merge drop-in config files from conf.d/ directory."""
        drop_in_dir = self._drop_in_dir()
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
        # Taken before reading, not after: a drop-in written while the read is
        # in progress then leaves the cache looking stale rather than current,
        # so the next call re-reads instead of latching a half-seen state.
        fingerprint = self._fingerprint()

        try:
            # Load the config file (should be created by debian postinstall)
            if not os.path.exists(self.config_file):
                logger.error(f"Config file {self.config_file} not found. Please ensure package is properly installed.")
                return self._cache_result(fingerprint, {})

            with open(self.config_file, 'r') as f:
                config = json.load(f)

            logger.debug(f"Loaded config from {self.config_file}: {config}")

            # Merge drop-in configs
            config = self._load_drop_ins(config)

            return self._cache_result(fingerprint, config)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {self.config_file}: {e}")
            return self._cache_result(fingerprint, {})
        except Exception as e:
            logger.error(f"Error loading config file {self.config_file}: {e}")
            return self._cache_result(fingerprint, {},
                                      time.monotonic() + TRANSIENT_RETRY_SECONDS)
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the loaded configuration, loading it if necessary
        
        Returns:
            Dictionary containing the configuration data
        """
        cache = self._cache
        if cache is None or cache[0] != self._fingerprint():
            return self.load_config()

        retry_at = cache[2]
        if retry_at is not None and time.monotonic() >= retry_at:
            return self.load_config()

        return cache[1]
    
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
        self._cache = None
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
