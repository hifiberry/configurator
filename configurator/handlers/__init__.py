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
    
    __all__ = ['SystemdHandler', 'SMBHandler', 'HostnameHandler', 'SoundcardHandler', 'SystemHandler']
except ImportError:
    # Flask not available - likely during testing or installation
    __all__ = []
