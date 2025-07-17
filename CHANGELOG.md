# Changelog

All notable changes to the HiFiBerry Configuration API will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.0] - 2025-07-17

### Added
- New API endpoint `GET /api/v1/systemd/service/{service}/exists` to check if a service exists
- Service existence validation for all systemd operations
- Enhanced error handling with HTTP 404 responses for non-existent services
- Configuration file JSON syntax validation and error handling
- Comprehensive API documentation for new endpoint and error responses

### Fixed
- Service existence check that was always returning false
- Improved service detection using `systemctl cat` instead of `systemctl list-unit-files`
- Fixed JSON syntax error in default configuration file (`configserver.json.default`)
- Enhanced systemd service management with better error reporting

### Changed
- All systemd API endpoints now validate service existence before operations
- Service list endpoint now includes `exists` field for each service
- Updated API documentation with new endpoint examples and error responses
- Error responses now include specific messages for service not found (404)

## [1.7.0] - 2025-07-17

### Added
- System-wide IPv6 enable/disable functionality to config-network
- IPv6 settings persistence across reboots using multiple configuration layers
- cmdline.txt kernel parameter management for Raspberry Pi compatibility
- sysctl settings and NetworkManager connection configuration for comprehensive IPv6 control
- Command-line options `--enable-ipv6` and `--disable-ipv6`
- Enhanced cmdline.py with IPv6 kernel parameter management methods
- Comprehensive manual pages for all configuration tools
- Manual pages installed to `/usr/share/man/man1/` for system-wide access
- REST API server for programmatic configuration access
- HTTP endpoints for ConfigDB CRUD operations
- systemd service for automatic API server startup on port 1081
- config-server command with comprehensive manual page
- Comprehensive API documentation with HTML and OpenAPI formats
- Automatic API server enablement and startup upon package installation

### Technical Details
- API server runs on port 1081 with JSON response format
- ConfigDB integration with encryption support for sensitive values
- systemd service management with permission-based access control
- Configuration file management with centralized parsing
- Debian package integration with proper postinstall scripts

## Version History

- **1.8.0** - Enhanced systemd API with service existence validation
- **1.7.0** - Added REST API server with systemd service management
- **1.6.x** - Previous versions (detailed history not available)
