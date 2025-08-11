#!/usr/bin/env python3
"""
Settings Manager for HiFiBerry Configuration Server

Provides a system for modules to register settings that should be saved/restored
across system restarts or configuration changes.
"""

import logging
from typing import Dict, Any, Optional, Callable
from .configdb import ConfigDB

logger = logging.getLogger(__name__)

class SettingsManager:
    """
    Manages saving and restoring of application settings using configdb.
    
    Settings are stored with the prefix 'saved-setting.' in configdb.
    Modules can register settings with save/restore callbacks.
    """
    
    def __init__(self, configdb: ConfigDB):
        """
        Initialize the settings manager
        
        Args:
            configdb: ConfigDB instance to use for storage
        """
        self.configdb = configdb
        self._registered_settings: Dict[str, Dict[str, Callable]] = {}
        self.setting_prefix = "saved-setting."
    
    def register_setting(self, setting_name: str, save_callback: Callable, restore_callback: Callable):
        """
        Register a setting with save and restore callbacks
        
        Args:
            setting_name: Name of the setting (will be prefixed with 'saved-setting.')
            save_callback: Function that returns the current setting value
            restore_callback: Function that takes a value and applies it
        """
        self._registered_settings[setting_name] = {
            'save': save_callback,
            'restore': restore_callback
        }
        logger.info(f"Registered setting: {setting_name}")
    
    def save_setting(self, setting_name: str) -> bool:
        """
        Save a specific setting using its registered save callback
        
        Args:
            setting_name: Name of the setting to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        if setting_name not in self._registered_settings:
            logger.error(f"Setting '{setting_name}' is not registered")
            return False
        
        try:
            save_callback = self._registered_settings[setting_name]['save']
            value = save_callback()
            
            if value is not None:
                key = f"{self.setting_prefix}{setting_name}"
                self.configdb.set(key, str(value))
                logger.info(f"Saved setting '{setting_name}' with value: {value}")
                return True
            else:
                logger.warning(f"Setting '{setting_name}' save callback returned None - not saving")
                return False
                
        except Exception as e:
            logger.error(f"Error saving setting '{setting_name}': {e}")
            return False
    
    def restore_setting(self, setting_name: str) -> bool:
        """
        Restore a specific setting using its registered restore callback
        
        Args:
            setting_name: Name of the setting to restore
            
        Returns:
            True if restored successfully, False otherwise
        """
        if setting_name not in self._registered_settings:
            logger.error(f"Setting '{setting_name}' is not registered")
            return False
        
        try:
            key = f"{self.setting_prefix}{setting_name}"
            value = self.configdb.get(key)
            
            if value is not None:
                restore_callback = self._registered_settings[setting_name]['restore']
                restore_callback(value)
                logger.info(f"Restored setting '{setting_name}' with value: {value}")
                return True
            else:
                logger.info(f"No saved value found for setting '{setting_name}'")
                return False
                
        except Exception as e:
            logger.error(f"Error restoring setting '{setting_name}': {e}")
            return False
    
    def save_all_settings(self) -> Dict[str, bool]:
        """
        Save all registered settings
        
        Returns:
            Dictionary mapping setting names to success status
        """
        results = {}
        for setting_name in self._registered_settings:
            results[setting_name] = self.save_setting(setting_name)
        
        successful = sum(results.values())
        total = len(results)
        logger.info(f"Saved {successful}/{total} settings")
        
        return results
    
    def restore_all_settings(self) -> Dict[str, bool]:
        """
        Restore all registered settings
        
        Returns:
            Dictionary mapping setting names to success status
        """
        results = {}
        for setting_name in self._registered_settings:
            results[setting_name] = self.restore_setting(setting_name)
        
        successful = sum(results.values())
        total = len(results)
        logger.info(f"Restored {successful}/{total} settings")
        
        return results
    
    def list_registered_settings(self) -> list:
        """
        Get list of registered setting names
        
        Returns:
            List of registered setting names
        """
        return list(self._registered_settings.keys())
    
    def list_saved_settings(self) -> Dict[str, str]:
        """
        Get all saved settings from configdb
        
        Returns:
            Dictionary mapping setting names to their saved values
        """
        all_keys = self.configdb.get_all(prefix=self.setting_prefix)
        saved_settings = {}
        
        for key, value in all_keys.items():
            # Remove the prefix to get the setting name
            setting_name = key[len(self.setting_prefix):]
            saved_settings[setting_name] = value
        
        return saved_settings
    
    def delete_saved_setting(self, setting_name: str) -> bool:
        """
        Delete a saved setting from configdb
        
        Args:
            setting_name: Name of the setting to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            key = f"{self.setting_prefix}{setting_name}"
            self.configdb.delete(key)
            logger.info(f"Deleted saved setting '{setting_name}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting saved setting '{setting_name}': {e}")
            return False
