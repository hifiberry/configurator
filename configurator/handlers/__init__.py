"""
API Handlers Package

Contains all API endpoint handlers for the HiFiBerry Configurator.
"""

try:
    from .systemd_handler import SystemdHandler
    from .smb_handler import SMBHandler
    from .hostname_handler import HostnameHandler
    from .soundcard_handler import SoundcardHandler
    from .system_handler import SystemHandler
    from .filesystem_handler import FilesystemHandler
    from .script_handler import ScriptHandler
    
    __all__ = ['SystemdHandler', 'SMBHandler', 'HostnameHandler', 'SoundcardHandler', 'SystemHandler', 'FilesystemHandler', 'ScriptHandler']
except ImportError:
    # Flask not available - likely during testing or installation
    __all__ = []
