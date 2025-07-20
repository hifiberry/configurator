"""
API Handlers Package

Contains all API endpoint handlers for the HiFiBerry Configurator.
"""

try:
    from .systemd_handler import SystemdHandler
    from .smb_handler import SMBHandler
    from .hostname_handler import HostnameHandler
    
    __all__ = ['SystemdHandler', 'SMBHandler', 'HostnameHandler']
except ImportError:
    # Flask not available - likely during testing or installation
    __all__ = []
