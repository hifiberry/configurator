"""
API Handlers Package

Contains all API endpoint handlers for the HiFiBerry Configurator.
"""

try:
    from .systemd_handler import SystemdHandler  # type: ignore[import-unused]
    from .smb_handler import SMBHandler  # type: ignore[import-unused]
    from .hostname_handler import HostnameHandler  # type: ignore[import-unused]
    from .soundcard_handler import SoundcardHandler  # type: ignore[import-unused]
    from .system_handler import SystemHandler  # type: ignore[import-unused]
    from .filesystem_handler import FilesystemHandler  # type: ignore[import-unused]
    from .script_handler import ScriptHandler  # type: ignore[import-unused]
    from .network_handler import NetworkHandler  # type: ignore[import-unused]
    from .i2c_handler import I2CHandler  # type: ignore[import-unused]
    from .volume_handler import VolumeHandler  # type: ignore[import-unused]
    from .bluetooth_handler import BluetoothHandler  # type: ignore[import-unused]
    from .player_registry_handler import PlayerRegistryHandler  # type: ignore[import-unused]
    from .ble_handler import BLEProvisioningHandler  # type: ignore[import-unused]

    __all__ = ['SystemdHandler', 'SMBHandler', 'HostnameHandler', 'SoundcardHandler', 'SystemHandler', 'FilesystemHandler', 'ScriptHandler', 'NetworkHandler', 'I2CHandler', 'VolumeHandler', 'BluetoothHandler', 'PlayerRegistryHandler', 'BLEProvisioningHandler']
except ImportError:
    # Flask not available - likely during testing or installation
    __all__ = []
