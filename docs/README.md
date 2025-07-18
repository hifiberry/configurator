# HiFiBerry Configuration API Documentation

This directory contains the documentation for the HiFiBerry Configuration API.

## Files

- `api-documentation.md` - Main API documentation covering all endpoints
- `README.md` - This file, explaining the documentation structure

## API Overview

The HiFiBerry Configuration API provides two main categories of endpoints:

### Configuration Management
- Key-value storage for system configuration
- Secure/encrypted value support
- Prefix-based filtering

### System Service Management
- Controlled systemd service operations
- Permission-based access control
- Service status monitoring

### SMB/CIFS Management (v1.9.0+)
- Network share discovery and configuration
- Systemd service-based mounting for reliability
- Secure credential storage with encryption
- Automatic mount management across reboots

## Maintaining the Documentation

The documentation is maintained in Markdown format in the `api-documentation.md` file.

To update the documentation:

1. Edit the `api-documentation.md` file directly
2. The file is copied to `/usr/share/doc/hifiberry-configurator/` during package installation
3. Update both endpoint descriptions and examples when adding new functionality

## Configuration File

The systemd API behavior is controlled by `/etc/configserver/configserver.json`:

```json
{
  "systemd": {
    "shairport": "all",
    "raat": "all",
    "mpd": "all"
  }
}
```

This configuration file is managed by the `ConfigParser` class, which provides centralized configuration management for all components.

## Security Model

- The configuration server runs with elevated privileges
- Service operations are strictly controlled by configuration file permissions
- Only explicitly configured services can be controlled
- Services default to "status" only access if not configured

## Version Updates

When updating the API version, remember to update:
- The version number in the Markdown title and content
- Any version-specific information in the content
- The version in the server.py file should match
- Add new endpoints to the documentation with examples
