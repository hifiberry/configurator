#!/usr/bin/env python3
"""
Version information for HiFiBerry Configurator
Single source of truth for version number
"""

__version__ = "2.9.1"
__version_info__ = tuple(map(int, __version__.split('.')))

# For backward compatibility
VERSION = __version__
