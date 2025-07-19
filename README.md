# HiFiBerry Configurator

A comprehensive system configuration toolkit for HiFiBerry audio devices, providing both command-line tools and a REST API for managing system settings.

## Features

### Configuration Management
- **Network Configuration**: Interface management, IPv6 control, and connectivity settings
- **Audio Configuration**: ALSA sound setup, sound card detection and configuration
- **System Configuration**: Raspberry Pi config.txt, kernel parameters, and HAT management
- **Storage & Sharing**: Samba client/mount management and volume control
- **Service Management**: systemd service control and monitoring

### Access Methods
- **Command-Line Tools**: Individual utilities for specific configuration tasks
- **REST API Server**: HTTP endpoints for programmatic configuration access
- **Configuration Database**: Centralized key-value storage with encryption support

### Platform Support
- Raspberry Pi with HiFiBerry HATs
- NetworkManager-based systems
- systemd-managed services

## Installation

This package is typically installed as part of HiFiBerry OS. For manual installation:

```bash
pip install -r requirements.txt
python setup.py install
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[API Documentation](docs/api-documentation.md)** - Complete REST API reference with examples
- **[Version Management](docs/version-management.md)** - Version management and release process

## Requirements

- Python 3.6+
- NetworkManager (for network configuration)
- Root privileges (for system configuration changes)

## License

MIT License - see LICENSE file for details.
