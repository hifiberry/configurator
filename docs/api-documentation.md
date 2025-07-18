# HiFiBerry Configuration API Documentation

**Version 1.8.0**

- [Endpoints](#endpoints)
  - [Version Information](#version-information)
  - [System Information](#system-information)
  - [Configuration Management](#configuration-management)
  - [System Service Management](#system-service-management)
  - [SMB/CIFS Management](#smbcifs-management)
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
    "systemd_operation": "/api/v1/systemd/service/<service>/<operation>",
    "smb_servers": "/api/v1/smb/servers",
    "smb_server_test": "/api/v1/smb/test/<server>",
    "smb_shares": "/api/v1/smb/shares/<server>",
    "smb_mounts": "/api/v1/smb/mounts",
    "smb_mount": "/api/v1/smb/mount",
    "smb_unmount": "/api/v1/smb/unmount",
    "smb_mount_by_id": "/api/v1/smb/mounts/mount/<int:mount_id>",
    "smb_unmount_by_id": "/api/v1/smb/mounts/unmount/<int:mount_id>"
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

### SMB/CIFS Management

The SMB/CIFS API provides functionality for discovering and mounting network shares containing music files. This enables accessing music libraries stored on NAS devices, Windows shares, or other SMB-compatible file servers.

**Security Features:**
- Passwords are automatically encrypted using the secure configuration store
- All credentials are stored securely and never exposed in plain text
- Mount configurations persist across system reboots
- Support for various SMB protocol versions (SMB1, SMB2, SMB3)

#### `GET /api/v1/smb/servers`

Discover SMB/CIFS file servers on the local network.

**Response:**
```json
{
  "status": "success",
  "data": {
    "servers": [
      {
        "ip": "192.168.1.100",
        "name": "MUSICSERVER",
        "hostname": "musicserver",
        "is_file_server": true,
        "services": ["File Server"],
        "local_network": "192.168.1.0/24",
        "interface": "eth0"
      },
      {
        "ip": "192.168.1.101",
        "name": "NAS",
        "hostname": "synology-nas",
        "is_file_server": true,
        "services": ["File Server"],
        "local_network": "192.168.1.0/24",
        "interface": "eth0"
      }
    ],
    "count": 2
  }
}
```

#### `POST /api/v1/smb/test/{server}`

Test connection to a specific SMB server.

**Parameters:**
- **server** (path, required): Server IP address or hostname

**Request Body:**
```json
{
  "server": "192.168.1.100",
  "username": "myuser",
  "password": "mypass"
}
```

**Request Body Parameters:**
- **server** (optional): Server IP address or hostname (overrides path parameter if provided)
- **username** (optional): Username for authentication
- **password** (optional): Password for authentication

**Response (Success - HTTP 200):**
```json
{
  "status": "success",
  "data": {
    "server": "192.168.1.100",
    "connected": true,
    "message": "Connection successful"
  }
}
```

**Response (Failure - HTTP 200):**
```json
{
  "status": "error",
  "message": "Connection failed",
  "data": {
    "server": "192.168.1.100",
    "connected": false,
    "error": "Authentication failed or server unreachable"
  }
}
```

#### `POST /api/v1/smb/shares`

List available shares on a specific SMB server.

**Request Body:**
```json
{
  "server": "192.168.1.100",
  "username": "test",
  "password": "password123",
  "detailed": true
}
```

**Parameters:**
- **server** (required): Server IP address or hostname
- **username** (optional): Username for authentication
- **password** (optional): Password for authentication
- **detailed** (optional): Set to true for detailed share information

**Response:**
```json
{
  "status": "success",
  "data": {
    "server": "192.168.1.100",
    "shares": [
      {
        "name": "music",
        "type": "Disk",
        "comment": "Music Library"
      },
      {
        "name": "media",
        "type": "Disk",
        "comment": "Media Files"
      },
      {
        "name": "backup",
        "type": "Disk",
        "comment": "Backup Storage"
      }
    ],
    "count": 3
  }
}
```

#### `GET /api/v1/smb/mounts`

List all configured SMB mount points for music access with real-time mount status.

**Response:**
```json
{
  "status": "success",
  "data": {
    "mounts": [
      {
        "id": 1,
        "server": "192.168.1.100",
        "share": "music",
        "mountpoint": "/data/music",
        "user": "musicuser",
        "version": "SMB3",
        "options": "rw,uid=1000,gid=1000",
        "mounted": true
      },
      {
        "id": 2,
        "server": "192.168.1.101",
        "share": "media",
        "mountpoint": "/data/nas-media",
        "user": "guest",
        "version": "SMB2",
        "options": "ro,uid=1000,gid=1000",
        "mounted": false
      }
    ],
    "count": 2,
    "summary": {
      "total": 2,
      "mounted": 1,
      "unmounted": 1
    }
  }
}
```

#### `POST /api/v1/smb/mount`

Add and mount a new SMB share for music access.

**Request Body:**
```json
{
  "server": "192.168.1.100",
  "share": "music",
  "mountpoint": "/data/music",
  "user": "musicuser",
  "password": "password123",
  "version": "SMB3",
  "options": "rw,uid=1000,gid=1000"
}
```

**Required Fields:**
- **server**: Server IP address or hostname
- **share**: Share name to mount

**Optional Fields:**
- **mountpoint**: Mount point path (default: `/data/{server}-{share}`)
- **user**: Username for authentication
- **password**: Password for authentication (automatically encrypted and stored securely)
- **version**: SMB protocol version (SMB1, SMB2, SMB3)
- **options**: Additional mount options

> **Security Note:** Passwords are automatically encrypted using the secure configuration store and are never stored in plain text.

**Response (Success):**
```json
{
  "status": "success",
  "message": "SMB share mounted successfully",
  "data": {
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "mounted": true
  }
}
```

**Response (Missing Content-Type):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Content-Type must be application/json"
}
```

**Response (Missing Request Body):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Missing request body"
}
```

**Response (Missing Required Fields):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Missing required fields: server and share"
}
```

**Response (Configuration Already Exists):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Mount configuration already exists",
  "error": "configuration_exists",
  "details": "Mount configuration for 192.168.1.100/music already exists"
}
```

**Response (Configuration Save Failed):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to save mount configuration",
  "error": "configuration_save_failed",
  "details": "Failed to save mount configuration for 192.168.1.100/music"
}
```

**Response (Internal Server Error):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to mount SMB share",
  "error": "Permission denied",
  "details": "An internal server error occurred while creating the mount"
}
```

#### `POST /api/v1/smb/unmount`

Unmount and remove an SMB share configuration.

**Request Body:**
```json
{
  "server": "192.168.1.100",
  "share": "music"
}
```

**Required Fields:**
- **server**: Server IP address or hostname
- **share**: Share name to unmount

**Response (Success):**
```json
{
  "status": "success",
  "message": "SMB share unmounted successfully",
  "data": {
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "unmounted": true
  }
}
```

**Response (Missing Content-Type):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Content-Type must be application/json"
}
```

**Response (Missing Request Body):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Missing request body"
}
```

**Response (Missing Required Fields):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Missing required fields: server and share"
}
```

**Response (Configuration Not Found):**
- HTTP 404 Not Found
```json
{
  "status": "error",
  "message": "Mount configuration not found for 192.168.1.100/music",
  "error": "Configuration not found",
  "details": "No mount configuration exists for server 192.168.1.100 and share music"
}
```

**Response (Internal Server Error):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to unmount SMB share",
  "error": "Device or resource busy",
  "details": "An internal server error occurred while removing the mount"
}
```

#### `POST /api/v1/smb/mounts/mount/<mount_id>`

Mount a specific SMB share by its configuration ID.

**URL Parameters:**
- **mount_id**: Mount configuration ID (integer)

**Example Request:**
```
POST /api/v1/smb/mounts/mount/1
```

**Response (Success):**
- HTTP 200 OK
```json
{
  "status": "success",
  "message": "SMB share mounted successfully",
  "data": {
    "id": 1,
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "mounted": true
  }
}
```

**Response (Not Found):**
- HTTP 404 Not Found
```json
{
  "status": "error",
  "message": "Mount configuration with ID 1 not found",
  "error": "mount_not_found",
  "details": "No mount configuration exists with the provided ID"
}
```

**Response (Mount Failed):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "mount error(13): Permission denied",
  "error": "mount error(13): Permission denied",
  "details": "Mount operation failed for 192.168.1.100/music",
  "data": {
    "id": 1,
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "mounted": false
  }
}
```

**Response (Internal Server Error):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to mount SMB share",
  "error": "Unexpected error occurred",
  "details": "An internal server error occurred while mounting the share"
}
```

#### `POST /api/v1/smb/mounts/unmount/<mount_id>`

Unmount a specific SMB share by its configuration ID.

**URL Parameters:**
- **mount_id**: Mount configuration ID (integer)

**Example Request:**
```
POST /api/v1/smb/mounts/unmount/1
```

**Response (Success):**
- HTTP 200 OK
```json
{
  "status": "success",
  "message": "SMB share unmounted successfully",
  "data": {
    "id": 1,
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "unmounted": true
  }
}
```

**Response (Not Found):**
- HTTP 404 Not Found
```json
{
  "status": "error",
  "message": "Mount configuration with ID 1 not found",
  "error": "mount_not_found",
  "details": "No mount configuration exists with the provided ID"
}
```

**Response (Unmount Failed):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "umount: /data/music: target is busy",
  "error": "umount: /data/music: target is busy",
  "details": "Unmount operation failed for 192.168.1.100/music",
  "data": {
    "id": 1,
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "mounted": true
  }
}
```

**Response (Internal Server Error):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to unmount SMB share",
  "error": "Unexpected error occurred",
  "details": "An internal server error occurred while unmounting the share"
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

### SMB/CIFS Management

**Discover SMB servers on the network:**
```bash
curl http://localhost:1081/api/v1/smb/servers
```

**Test connection to a server (using URL path):**
```bash
curl -X POST http://localhost:1081/api/v1/smb/test/192.168.1.100 \
  -H "Content-Type: application/json"
```

**Test connection with server in request body:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/test/placeholder \
  -H "Content-Type: application/json" \
  -d '{"server": "192.168.1.100"}'
```

**Test connection with authentication:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/test/192.168.1.100 \
  -H "Content-Type: application/json" \
  -d '{"username": "musicuser", "password": "mypass"}'
```

**Test connection with server and authentication in body:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/test/placeholder \
  -H "Content-Type: application/json" \
  -d '{"server": "192.168.1.100", "username": "musicuser", "password": "mypass"}'
```

**List shares on a server:**
```bash
curl http://localhost:1081/api/v1/smb/shares/192.168.1.100
```

**List shares with authentication:**
```bash
curl "http://localhost:1081/api/v1/smb/shares/192.168.1.100?username=musicuser&password=mypass"
```

**Get detailed share information:**
```bash
curl "http://localhost:1081/api/v1/smb/shares/192.168.1.100?detailed=true"
```

**List all configured mounts:**
```bash
curl http://localhost:1081/api/v1/smb/mounts
```

**Mount a music share:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "server": "192.168.1.100",
       "share": "music",
       "mountpoint": "/data/music",
       "user": "musicuser",
       "password": "mypass",
       "version": "SMB3",
       "options": "rw,uid=1000,gid=1000"
     }' \
     http://localhost:1081/api/v1/smb/mount
```

**Mount with minimal configuration (guest access):**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "server": "192.168.1.100",
       "share": "public-music"
     }' \
     http://localhost:1081/api/v1/smb/mount
```

**Unmount a share:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "server": "192.168.1.100",
       "share": "music"
     }' \
     http://localhost:1081/api/v1/smb/unmount
```

**Mount a share by ID:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/mounts/mount/1
```

**Unmount a share by ID:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/mounts/unmount/1
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
