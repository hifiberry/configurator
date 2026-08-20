"""
API Handlers Package

Contains all API endpoint handlers for the HiFiBerry Configurator.
"""

import logging

logger = logging.getLogger(__name__)

# Name of the dependency that could not be imported, or None when everything
# loaded. Callers use it to skip work that cannot run, and to say WHY.
MISSING_DEPENDENCY = None

try:
    from .systemd_handler import SystemdHandler
    from .smb_handler import SMBHandler
    from .hostname_handler import HostnameHandler
    from .soundcard_handler import SoundcardHandler
    from .system_handler import SystemHandler
    from .filesystem_handler import FilesystemHandler
    from .script_handler import ScriptHandler
    from .network_handler import NetworkHandler
    from .i2c_handler import I2CHandler
    from .volume_handler import VolumeHandler
    from .bluetooth_handler import BluetoothHandler
    from .player_registry_handler import PlayerRegistryHandler
    from .ble_handler import BLEProvisioningHandler
    from .extensions_handler import ExtensionsHandler

    __all__ = ['SystemdHandler', 'SMBHandler', 'HostnameHandler', 'SoundcardHandler', 'SystemHandler', 'FilesystemHandler', 'ScriptHandler', 'NetworkHandler', 'I2CHandler', 'VolumeHandler', 'BluetoothHandler', 'PlayerRegistryHandler', 'BLEProvisioningHandler', 'ExtensionsHandler']
except ImportError as exc:
    # An optional runtime dependency is missing. That is expected in a dev
    # checkout or the build chroot -- debian/rules sets PYBUILD_DISABLE=test
    # precisely because this suite needs runtime modules the chroot lacks --
    # so degrading to an empty __all__ is right.
    #
    # But record WHICH module, and say so. Swallowing the name is how a
    # missing python3-netifaces (imported via smb_handler -> sambaclient)
    # surfaced two files away as "cannot import name 'SMBHandler' from
    # configurator.handlers", sending the reader after a handler that was
    # perfectly fine, and aborting collection of the entire test suite with
    # no mention of netifaces anywhere.
    MISSING_DEPENDENCY = getattr(exc, "name", None) or str(exc)
    logger.warning(
        f"configurator.handlers is unavailable: cannot import "
        f"{MISSING_DEPENDENCY!r}. API handlers will not be registered.")
    __all__ = []
