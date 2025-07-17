# HiFiBerry Configuration API Documentation

**Version 1.8.0**

- [Endpoints](#endpoints)
  - [Version Information](#version-information)
  - [System Information](#system-information)
  - [Configuration Management](#configuration-management)
  - [System Service Management](#system-service-management)
- [Configuration File](#configuration-file)
- [Examples](#examples)
- [Error Codes](#error-codes)

## Overview

The HiFiBerry Configuration API provides REST endpoints for managing configuration settings and system services in the HiFiBerry system. All responses are in JSON format with consistent structure.

**Base URL:** `http://localhost:1081`

> **Note:** Replace localhost:1081 with your actual server address and port.

## Endpoints

### Version Information

#### `GET /version`

Get version information and available endpoints.

**Response:**
```json
{
  "service": "hifiberry-config-api",
  "version": "1.8.0",
  "api_version": "v1",
  "description": "HiFiBerry Configuration Server",
  "endpoints": {
    "version": "/version",
    "systeminfo": "/api/v1/systeminfo",
    "keys": "/api/v1/keys",
    "key": "/api/v1/key/<key>",
    "systemd_services": "/api/v1/systemd/services",
    "systemd_service": "/api/v1/systemd/service/<service>",
    "systemd_service_exists": "/api/v1/systemd/service/<service>/exists",
    "systemd_operation": "/api/v1/systemd/service/<service>/<operation>"
  }
}
```

### System Information

#### `GET /api/v1/systeminfo`

Get system information including Pi model, HAT details, sound card information, and system UUID.

**Response:**
```json
{
  "pi_model": {
    "name": "Raspberry Pi 4 Model B Rev 1.4",
    "version": "4"
  },
  "hat_info": {
    "vendor": "HiFiBerry",
    "product": "DAC+ Pro",
    "uuid": "12345678-1234-1234-1234-123456789abc",
    "vendor_card": "HiFiBerry:DAC+ Pro"
  },
  "soundcard": {
    "name": "DAC+ Pro",
    "volume_control": "Digital",
    "hardware_index": 0,
    "output_channels": 2,
    "input_channels": 0,
    "features": ["usehwvolume"],
    "hat_name": "DAC+ Pro",
    "supports_dsp": false,
    "card_type": ["DAC"]
  },
  "system": {
    "uuid": "abcd1234-5678-90ef-1234-567890abcdef"
  },
  "status": "success"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Failed to retrieve system information",
  "error": "Error details"
}
```

### Configuration Management

#### `GET /api/v1/keys`

Get all configuration keys only (without values).

**Parameters:**
- **prefix** (query, optional): Filter keys by prefix

**Response:**
```json
{
  "status": "success",
  "data": ["volume", "soundcard"],
  "count": 2
}
```

#### `GET /api/v1/key/{key}`

Get a specific configuration value by key.

**Parameters:**
- **key** (path, required): Configuration key name
- **secure** (query, optional): Set to "true" for secure/encrypted values
- **default** (query, optional): Default value if key not found

**Response:**
```json
{
  "status": "success",
  "data": {
    "key": "volume",
    "value": "75"
  }
}
```

#### `POST` / `PUT /api/v1/key/{key}`

Set or update a configuration value.

**Parameters:**
- **key** (path, required): Configuration key name
- **Content-Type** (header, required): application/json

**Request Body:**
- **value** (required): The value to set
- **secure** (optional): Store as encrypted value

**Request Body Example:**
```json
{
  "value": "75",
  "secure": false
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Configuration key \"volume\" set successfully",
  "data": {
    "key": "volume",
    "value": "75"
  }
}
```

#### `DELETE /api/v1/key/{key}`

Delete a configuration key and its value.

**Parameters:**
- **key** (path, required): Configuration key name

**Response:**
```json
{
  "status": "success",
  "message": "Configuration key \"volume\" deleted successfully"
}
```

### System Service Management

The systemd API allows controlled management of system services based on permissions defined in the configuration file.

#### `GET /api/v1/systemd/services`

List all configured services and their permissions.

**Response:**
```json
{
  "status": "success",
  "data": {
    "services": [
      {
        "service": "shairport",
        "permission_level": "all",
        "allowed_operations": ["start", "stop", "restart", "enable", "disable", "status"],
        "active": "active",
        "enabled": "enabled"
      },
      {
        "service": "mpd",
        "permission_level": "all",
        "allowed_operations": ["start", "stop", "restart", "enable", "disable", "status"],
        "active": "inactive",
        "enabled": "disabled"
      }
    ],
    "count": 2
  }
}
```

#### `GET /api/v1/systemd/service/{service}`

Get detailed status of a specific service.

**Parameters:**
- **service** (path, required): Service name

**Response:**
```json
{
  "status": "success",
  "data": {
    "service": "shairport",
    "active": "active",
    "enabled": "enabled",
    "status_output": "● shairport.service - Shairport Sync...",
    "status_returncode": 0,
    "allowed_operations": ["start", "stop", "restart", "enable", "disable", "status"]
  }
}
```

#### `GET /api/v1/systemd/service/{service}/exists`

Check if a systemd service exists on the system.

**Parameters:**
- **service** (path, required): Service name

**Response (Service Exists):**
```json
{
  "status": "success",
  "data": {
    "service": "shairport",
    "exists": true,
    "active": "active",
    "enabled": "enabled",
    "allowed_operations": ["start", "stop", "restart", "enable", "disable", "status"]
  }
}
```

**Response (Service Does Not Exist):**
```json
{
  "status": "success",
  "data": {
    "service": "nonexistent-service",
    "exists": false
  }
}
```

#### `POST /api/v1/systemd/service/{service}/{operation}`

Execute a systemd operation on a service.

**Parameters:**
- **service** (path, required): Service name
- **operation** (path, required): Operation to perform (start, stop, restart, enable, disable, status)

**Valid Operations:**
- `start` - Start the service
- `stop` - Stop the service
- `restart` - Restart the service
- `enable` - Enable the service for automatic startup
- `disable` - Disable the service from automatic startup
- `status` - Get service status (always allowed)

**Response (Success):**
```json
{
  "status": "success",
  "message": "Successfully executed start on shairport",
  "data": {
    "service": "shairport",
    "operation": "start",
    "output": "",
    "returncode": 0
  }
}
```

**Response (Permission Denied):**
```json
{
  "status": "error",
  "message": "Operation \"start\" not allowed for service \"restricted-service\". Allowed operations: [\"status\"]"
}
```

**Response (Service Not Found):**
```json
{
  "status": "error",
  "message": "Service \"nonexistent-service\" does not exist on the system"
}
```

## Configuration File

The systemd API is controlled by `/etc/configserver/configserver.json`:

```json
{
  "systemd": {
    "shairport": "all",
    "raat": "all",
    "mpd": "all"
  }
}
```

**Permission Levels:**
- `"all"` - Allows all operations: start, stop, restart, enable, disable, status
- `"status"` - Allows only status checking
- No entry - Defaults to "status" only

The configuration file is managed by the `ConfigParser` class, which provides centralized configuration management for all components.

## Examples

### Configuration Management

**Get version information:**
```bash
curl http://localhost:1081/version
```

**Get system information:**
```bash
curl http://localhost:1081/api/v1/systeminfo
```

**Get all configuration keys:**
```bash
curl http://localhost:1081/api/v1/keys
```

**Get specific configuration value:**
```bash
curl http://localhost:1081/api/v1/key/volume
```

**Set configuration value:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"value":"75"}' \
     http://localhost:1081/api/v1/key/volume
```

**Set secure/encrypted value:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"value":"secret","secure":true}' \
     http://localhost:1081/api/v1/key/password
```

**Delete configuration:**
```bash
curl -X DELETE http://localhost:1081/api/v1/key/volume
```

### System Service Management

**List all configured services:**
```bash
curl http://localhost:1081/api/v1/systemd/services
```

**Get service status:**
```bash
curl http://localhost:1081/api/v1/systemd/service/shairport
```

**Check if service exists:**
```bash
curl http://localhost:1081/api/v1/systemd/service/shairport/exists
```

**Start a service:**
```bash
curl -X POST http://localhost:1081/api/v1/systemd/service/shairport/start
```

**Stop a service:**
```bash
curl -X POST http://localhost:1081/api/v1/systemd/service/shairport/stop
```

**Restart a service:**
```bash
curl -X POST http://localhost:1081/api/v1/systemd/service/shairport/restart
```

**Enable a service:**
```bash
curl -X POST http://localhost:1081/api/v1/systemd/service/shairport/enable
```

**Disable a service:**
```bash
curl -X POST http://localhost:1081/api/v1/systemd/service/shairport/disable
```

## Error Responses

| HTTP Code | Description | Example Response |
|-----------|-------------|------------------|
| 400 | Bad Request | `{"status": "error", "message": "Missing required field: value"}` |
| 403 | Forbidden | `{"status": "error", "message": "Operation \"start\" not allowed for service \"restricted-service\". Allowed operations: [\"status\"]"}` |
| 404 | Not Found | `{"status": "error", "message": "Configuration key not found"}` or `{"status": "error", "message": "Service \"nonexistent-service\" does not exist on the system"}` |
| 500 | Internal Server Error | `{"status": "error", "message": "Failed to retrieve configuration data"}` |

## Security Considerations

- The configuration server runs with elevated privileges to manage system services
- Service operations are strictly controlled by the configuration file permissions
- Only services explicitly configured in `/etc/configserver/configserver.json` can be controlled
- Services not listed or marked as "status" only allow status checking
- All systemd operations have a 30-second timeout to prevent hanging requests

---

*HiFiBerry Configuration API v1.8.0*
