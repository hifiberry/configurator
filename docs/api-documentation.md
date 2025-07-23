# HiFiBerry Configuration API Documentation

**Version 2.1.0**

- [Endpoints](#endpoints)
  - [Version Information](#version-information)
  - [System Information](#system-information)
  - [Configuration Management](#configuration-management)
  - [System Service Management](#system-service-management)
  - [SMB/CIFS Management](#smbcifs-management)
  - [Hostname Management](#hostname-management)
  - [Soundcard Management](#soundcard-management)
  - [System Management](#system-management)
  - [Filesystem Management](#filesystem-management)
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
  "version": "2.1.0",
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
    "smb_mount_config": "/api/v1/smb/mount",
    "smb_mount_all": "/api/v1/smb/mount-all",
    "hostname": "/api/v1/hostname",
    "soundcards": "/api/v1/soundcards",
    "soundcard_dtoverlay": "/api/v1/soundcard/dtoverlay",
    "system_reboot": "/api/v1/system/reboot",
    "system_shutdown": "/api/v1/system/shutdown",
    "filesystem_symlinks": "/api/v1/filesystem/symlinks"
  }
}
```

### System Information

#### `GET /api/v1/systeminfo`

Get system information including Pi model, HAT details, sound card information, system UUID, and hostname information.

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
    "uuid": "abcd1234-5678-90ef-1234-567890abcdef",
    "hostname": "hifiberry-player",
    "pretty_hostname": "HiFiBerry Music Player"
  },
  "status": "success"
}
```

**Response (Error):**
```json
{
  "pi_model": {
    "name": "unknown",
    "version": "unknown"
  },
  "hat_info": {
    "vendor": null,
    "product": null,
    "uuid": null,
    "vendor_card": "unknown:unknown"
  },
  "soundcard": {
    "name": "unknown",
    "volume_control": null,
    "hardware_index": null,
    "output_channels": 0,
    "input_channels": 0,
    "features": [],
    "hat_name": null,
    "supports_dsp": false,
    "card_type": []
  },
  "system": {
    "uuid": null,
    "hostname": null,
    "pretty_hostname": null
  },
  "status": "error",
  "error": "Failed to collect system info"
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

**Version 2.0.0 Changes:**
- Unified mount/unmount operations into single `/api/v1/smb/mount` endpoint with action parameter
- Removed separate `/api/v1/smb/unmount` endpoint (BREAKING CHANGE)
- Added required `action` field to mount requests ("add" or "remove")
- Mount operations are now handled by the systemd service for better reliability
- Individual mount/unmount by ID endpoints have been removed
- New `/api/v1/smb/mount-all` endpoint triggers the sambamount systemd service
- Mount and unmount endpoints now only manage configurations, not active mounts

**Workflow:**
1. Use `/api/v1/smb/mount` with `"action": "add"` to create share configurations
2. Use `/api/v1/smb/mount-all` to restart sambamount service and mount all configured shares
3. Use `/api/v1/smb/mount` with `"action": "remove"` to remove configurations
4. Use `/api/v1/smb/mount-all` again to restart sambamount service - this will automatically unmount removed shares and mount remaining ones

**Smart Cleanup:**
- The system tracks which shares were previously mounted in `/tmp/sambamount_state.json`
- When `/api/v1/smb/mount-all` is called, it compares current configuration with previous state
- Shares that are no longer configured are automatically unmounted before mounting current shares
- State file is automatically cleaned up on system reboot for fresh startup

**Security Features:**
- Passwords are automatically encrypted using the secure configuration store
- All credentials are stored securely and never exposed in plain text
- Mount configurations persist across system reboots
- Support for various SMB protocol versions (SMB1, SMB2, SMB3)
- Systemd service runs with proper permissions for system-wide mount visibility

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

Create or remove SMB share configurations.

> **Note:** This endpoint only manages configurations. To mount all configured shares, use the `/api/v1/smb/mount-all` endpoint.

**Request Body:**
```json
{
  "action": "add",
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
- **action**: Action to perform ("add" to create configuration, "remove" to delete configuration)
- **server**: Server IP address or hostname
- **share**: Share name

**Optional Fields (for action "add"):**
- **mountpoint**: Mount point path (default: `/data/{server}-{share}`)
- **user**: Username for authentication
- **password**: Password for authentication (automatically encrypted and stored securely)
- **version**: SMB protocol version (SMB1, SMB2, SMB3)
- **options**: Additional mount options

> **Security Note:** Passwords are automatically encrypted using the secure configuration store and are never stored in plain text.

**Response (Add Success):**
```json
{
  "status": "success",
  "message": "SMB share configuration created successfully",
  "data": {
    "action": "add",
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "note": "Configuration saved. Use /api/v1/smb/mount-all to mount all configured shares."
  }
}
```

**Response (Remove Success):**
```json
{
  "status": "success",
  "message": "SMB share configuration removed successfully",
  "data": {
    "action": "remove",
    "server": "192.168.1.100",
    "share": "music",
    "mountpoint": "/data/music",
    "note": "Configuration removed. Restart sambamount service to apply changes to active mounts."
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

**Response (Missing Action Field):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Missing required field: action. Must be 'add' or 'remove'"
}
```

**Response (Invalid Action):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Invalid action. Must be 'add' or 'remove'"
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
  "message": "Missing required fields: action, server and share"
}
```

**Response (Configuration Already Exists - for action "add"):**
- HTTP 400 Bad Request
```json
{
  "status": "error",
  "message": "Mount configuration already exists",
  "error": "configuration_exists",
  "details": "Mount configuration for 192.168.1.100/music already exists"
}
```

**Response (Configuration Not Found - for action "remove"):**
- HTTP 404 Not Found
```json
{
  "status": "error",
  "message": "Mount configuration not found for 192.168.1.100/music",
  "error": "Configuration not found",
  "details": "No mount configuration exists for server 192.168.1.100 and share music"
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
  "message": "Failed to process SMB share configuration",
  "error": "Permission denied",
  "details": "An internal server error occurred while processing the mount configuration"
}
```

#### `POST /api/v1/smb/mount-all`

Mount all configured Samba shares by restarting the sambamount systemd service.

> **Note:** This endpoint restarts the sambamount.service which will mount all configured SMB shares. Restarting ensures a fresh mount operation and applies any new configurations. The service runs with proper permissions to make mounts visible system-wide.
> 
> **Smart Cleanup:** The endpoint tracks previously mounted shares and automatically unmounts any shares that are no longer configured. This state is reset on system reboot to ensure clean startup.

**Request Body:** None required

**Response (Success):**
```json
{
  "status": "success",
  "message": "Samba mount service restarted successfully",
  "data": {
    "service": "sambamount.service",
    "action": "restarted",
    "configurations": [
      {
        "server": "192.168.1.100",
        "share": "music",
        "mountpoint": "/data/music",
        "id": 1
      },
      {
        "server": "192.168.1.27",
        "share": "data",
        "mountpoint": "/mnt/data",
        "id": 2
      }
    ],
    "count": 2,
    "cleanup": {
      "unmounted_shares": [
        {
          "mount_key": "192.168.1.100/old-share",
          "mountpoint": "/data/old-share",
          "status": "unmounted"
        }
      ],
      "count": 1
    },
    "note": "Check service logs with: journalctl -u sambamount.service -f"
  }
}
```

> **Note:** The `cleanup` section appears only when shares were automatically unmounted because they were removed from the configuration.

**Response (Service Restart Failed):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to restart Samba mount service",
  "error": "Service restart failed",
  "details": "Job for sambamount.service failed because the control process exited with error code",
  "data": {
    "service": "sambamount.service",
    "action": "restart_failed",
    "return_code": 1
  }
}
```

**Response (Service Restart Timeout):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Timeout restarting Samba mount service",
  "error": "Service restart timeout",
  "details": "Timeout restarting sambamount.service after 30 seconds"
}
```

**Response (Internal Server Error):**
- HTTP 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Failed to restart Samba mount service",
  "error": "Unexpected error occurred",
  "details": "An internal server error occurred while restarting the service"
}
```

## Hostname Management

### `GET /api/v1/hostname`

Get current system hostname and pretty hostname.

**Response:**
```json
{
  "status": "success",
  "data": {
    "hostname": "hifiberry",
    "pretty_hostname": "My HiFiBerry System"
  }
}
```

**Response Fields:**
- **hostname**: Current system hostname (DNS-compatible, lowercase, max 16 chars)
- **pretty_hostname**: Current pretty hostname (human-readable, can be null if not set)

### `POST /api/v1/hostname`

Set system hostname and/or pretty hostname.

**Request Body:**
```json
{
  "hostname": "new-hostname",
  "pretty_hostname": "My New HiFiBerry System"
}
```

**Request Parameters:**
- **hostname** (optional): System hostname to set (max 64 chars, ASCII letters/numbers/hyphens, no leading/trailing hyphens)
- **pretty_hostname** (optional): Pretty hostname to set (max 64 chars, printable ASCII characters)

**Notes:**
- You must provide at least one of `hostname` or `pretty_hostname`
- If only `pretty_hostname` is provided, the system hostname will be automatically derived from it
- The derived hostname will be sanitized (lowercase, spaces become hyphens, special chars removed)
- When setting a hostname, `/etc/hosts` is automatically updated to include the new hostname as 127.0.0.1
- Old hostname entries are removed from `/etc/hosts` when changing hostnames

**Example Request - Set both:**
```json
{
  "hostname": "music-server",
  "pretty_hostname": "Music Server"
}
```

**Example Request - Set only pretty hostname:**
```json
{
  "pretty_hostname": "My HiFiBerry Music System"
}
```

**Success Response:**
```json
{
  "status": "success",
  "message": "Hostname updated successfully",
  "data": {
    "hostname": "music-server",
    "pretty_hostname": "Music Server"
  }
}
```

**Error Responses:**

Invalid hostname format:
```json
{
  "status": "error",
  "message": "Invalid hostname format (max 64 chars, ASCII letters/numbers/hyphens, no leading/trailing hyphens)"
}
```

Invalid pretty hostname:
```json
{
  "status": "error",
  "message": "Invalid pretty hostname format"
}
```

Missing parameters:
```json
{
  "status": "error",
  "message": "Must provide either hostname or pretty_hostname"
}
```

## Soundcard Management

### `GET /api/v1/soundcards`

List all available HiFiBerry sound cards with their specifications and device tree overlay information.

**Response:**
```json
{
  "status": "success",
  "data": {
    "soundcards": [
      {
        "name": "DAC8x/ADC8x",
        "dtoverlay": "hifiberry-dac8x",
        "volume_control": null,
        "output_channels": 8,
        "input_channels": 8,
        "features": [],
        "supports_dsp": false,
        "card_type": ["DAC", "ADC"],
        "is_pro": false
      },
      {
        "name": "Digi2 Pro",
        "dtoverlay": "hifiberry-digi-pro",
        "volume_control": "Softvol",
        "output_channels": 2,
        "input_channels": 0,
        "features": ["dsp"],
        "supports_dsp": true,
        "card_type": ["Digi"],
        "is_pro": true
      }
    ],
    "count": 20
  }
}
```

**Response Fields:**
- **soundcards**: Array of sound card objects
- **count**: Total number of available sound cards

**Sound Card Object Fields:**
- **name**: Display name of the sound card
- **dtoverlay**: Device tree overlay required in config.txt
- **volume_control**: Volume control method (null if no hardware volume control)
- **output_channels**: Number of output audio channels
- **input_channels**: Number of input audio channels
- **features**: Array of special features (e.g., "dsp", "toslink", "analoginput")
- **supports_dsp**: Boolean indicating if the card supports DSP processing
- **card_type**: Array of card types (e.g., "DAC", "ADC", "Amp", "Digi")
- **is_pro**: Boolean indicating if this is a professional-grade card

### `POST /api/v1/soundcard/dtoverlay`

Set the device tree overlay in config.txt for sound card configuration. This endpoint only accepts valid HiFiBerry sound card overlays.

**Request Body:**
```json
{
  "dtoverlay": "hifiberry-dac",
  "remove_existing": true
}
```

**Request Parameters:**
- **dtoverlay** (required): Device tree overlay name (must be from the supported HiFiBerry sound cards list)
- **remove_existing** (optional): Remove existing HiFiBerry overlays before setting new one (default: true)

**Success Response:**
```json
{
  "status": "success",
  "message": "Successfully set dtoverlay to 'hifiberry-dac' (removed existing HiFiBerry overlays)",
  "data": {
    "dtoverlay": "hifiberry-dac",
    "changes_made": true,
    "reboot_required": true
  }
}
```

**Success Response (No Changes):**
```json
{
  "status": "success",
  "message": "dtoverlay 'hifiberry-dac' was already configured",
  "data": {
    "dtoverlay": "hifiberry-dac",
    "changes_made": false,
    "reboot_required": false
  }
}
```

**Response Fields:**
- **dtoverlay**: The overlay that was set
- **changes_made**: Boolean indicating if config.txt was modified
- **reboot_required**: Boolean indicating if a system reboot is needed

**Error Responses:**

Missing dtoverlay parameter:
```json
{
  "status": "error",
  "message": "dtoverlay parameter is required"
}
```

Invalid dtoverlay:
```json
{
  "status": "error",
  "message": "Invalid dtoverlay 'invalid-overlay'. Must be one of the supported HiFiBerry overlays.",
  "valid_overlays": [
    "hifiberry-amp",
    "hifiberry-amp100,automute",
    "hifiberry-amp3",
    "hifiberry-amp4pro",
    "hifiberry-dac",
    "hifiberry-dac8x",
    "hifiberry-dacplus-std",
    "hifiberry-dacplushd",
    "hifiberry-dacplusadc",
    "hifiberry-dacplusadcpro",
    "hifiberry-dacplusdsp",
    "hifiberry-digi",
    "hifiberry-digi-pro"
  ]
}
```

Permission error:
```json
{
  "status": "error",
  "message": "Failed to set dtoverlay",
  "error": "Permission denied: /boot/firmware/config.txt"
}
```

**Notes:**
- This endpoint validates that the requested dtoverlay is from a supported HiFiBerry sound card
- The list of valid overlays can be retrieved from the `/api/v1/soundcards` endpoint
- Changes to config.txt require a system reboot to take effect
- The API automatically creates a backup of config.txt before making changes
- If `remove_existing` is true (default), existing HiFiBerry overlays will be removed first

## System Management

### `POST /api/v1/system/reboot`

Reboot the system after an optional delay. This endpoint provides a safe way to restart the system remotely.

**Request Body (Optional):**
```json
{
  "delay": 10
}
```

**Request Parameters:**
- **delay** (optional): Number of seconds to wait before rebooting (0-300 seconds, default: 5)

**Success Response:**
```json
{
  "status": "success",
  "message": "System reboot scheduled in 5 seconds",
  "data": {
    "delay": 5,
    "scheduled": true
  }
}
```

**Error Responses:**

Invalid delay value:
```json
{
  "status": "error",
  "message": "Delay must be between 0 and 300 seconds"
}
```

Invalid delay format:
```json
{
  "status": "error",
  "message": "Delay must be a valid integer"
}
```

Server error:
```json
{
  "status": "error",
  "message": "Failed to schedule system reboot",
  "error": "Permission denied"
}
```

### `POST /api/v1/system/shutdown`

Shutdown the system after an optional delay. This endpoint provides a safe way to power off the system remotely.

**Request Body (Optional):**
```json
{
  "delay": 10
}
```

**Request Parameters:**
- **delay** (optional): Number of seconds to wait before shutting down (0-300 seconds, default: 5)

**Success Response:**
```json
{
  "status": "success",
  "message": "System shutdown scheduled in 5 seconds",
  "data": {
    "delay": 5,
    "scheduled": true
  }
}
```

**Error Responses:**

Invalid delay value:
```json
{
  "status": "error",
  "message": "Delay must be between 0 and 300 seconds"
}
```

Invalid delay format:
```json
{
  "status": "error",
  "message": "Delay must be a valid integer"
}
```

Server error:
```json
{
  "status": "error",
  "message": "Failed to schedule system shutdown",
  "error": "Permission denied"
}
```

**Notes:**
- Both endpoints execute the operation in a background thread to allow the API response to be sent before the system shuts down
- The delay parameter allows time for the API response to be delivered and any cleanup operations to complete
- Operations require sudo privileges and will fail if the API server doesn't have the necessary permissions
- The system will log the operation before executing it
- Maximum delay is 5 minutes (300 seconds) for safety

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

**Create a music share configuration:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "action": "add",
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

**Create configuration with minimal settings (guest access):**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "action": "add",
       "server": "192.168.1.100",
       "share": "public-music"
     }' \
     http://localhost:1081/api/v1/smb/mount
```

**Mount all configured shares via systemd service:**
```bash
curl -X POST http://localhost:1081/api/v1/smb/mount-all
```

**Remove a share configuration:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "action": "remove",
       "server": "192.168.1.100",
       "share": "music"
     }' \
     http://localhost:1081/api/v1/smb/mount
```

### System Management

**Reboot the system immediately:**
```bash
curl -X POST http://localhost:1081/api/v1/system/reboot
```

**Reboot the system with 30 second delay:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"delay": 30}' \
     http://localhost:1081/api/v1/system/reboot
```

**Shutdown the system immediately:**
```bash
curl -X POST http://localhost:1081/api/v1/system/shutdown
```

**Shutdown the system with 60 second delay:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"delay": 60}' \
     http://localhost:1081/api/v1/system/shutdown
```

### Filesystem Management

**List symlinks in MPD music directory:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"directory": "/var/lib/mpd/music/"}' \
     http://localhost:1081/api/v1/filesystem/symlinks
```

**List symlinks with error handling:**
```bash
# This will fail if directory is not in allowed destinations
curl -X POST -H "Content-Type: application/json" \
     -d '{"directory": "/unauthorized/path/"}' \
     http://localhost:1081/api/v1/filesystem/symlinks
```

### Filesystem Management

#### `POST /api/v1/filesystem/symlinks`

List all symlinks in a specified directory, including their destinations. The directory must be configured in the server's allowed destinations list.

**Security:** Access is restricted to directories listed in `allowed_symlink_destinations` configuration. Without configuration, no directories are accessible.

**Request Body:**
```json
{
  "directory": "/var/lib/mpd/music/"
}
```

**Parameters:**
- `directory` (string, required): Directory path to scan for symlinks. Must be in allowed destinations list.

**Success Response (200):**
```json
{
  "status": "success",
  "message": "Symlinks listed successfully",
  "data": {
    "directory": "/var/lib/mpd/music/",
    "symlinks": [
      {
        "name": "MyMusic",
        "path": "/var/lib/mpd/music/MyMusic",
        "target": "/data/nas-music/collection",
        "absolute_target": "/data/nas-music/collection",
        "target_exists": true,
        "modified": 1642781234.567,
        "permissions": "755"
      },
      {
        "name": "Archive",
        "path": "/var/lib/mpd/music/Archive",
        "target": "../backup/old-music",
        "absolute_target": "/var/lib/mpd/backup/old-music",
        "target_exists": false,
        "modified": 1642781134.432,
        "permissions": "755"
      }
    ],
    "count": 2
  }
}
```

**Error Response (403 - Directory Not Allowed):**
```json
{
  "status": "error",
  "message": "Directory is not in allowed destinations",
  "error": "directory_not_allowed",
  "data": {
    "directory": "/unauthorized/path/",
    "allowed_destinations": ["/var/lib/mpd/music/"]
  }
}
```

**Error Response (404 - Directory Not Found):**
```json
{
  "status": "error",
  "message": "Directory does not exist",
  "data": {
    "directory": "/nonexistent/path/"
  }
}
```

**Error Response (403 - No Configuration):**
```json
{
  "status": "error",
  "message": "Directory access is not allowed - no destinations configured",
  "error": "directory_access_not_allowed"
}
```

**Response Fields:**
- `name`: Symlink filename
- `path`: Full path to the symlink
- `target`: Raw symlink target (as stored in the symlink)
- `absolute_target`: Resolved absolute path of the target
- `target_exists`: Boolean indicating if the target exists
- `modified`: Unix timestamp of symlink modification time
- `permissions`: Octal permission string
- `error`: Error message if symlink details cannot be accessed

## Configuration File

The server configuration file `/usr/share/hifiberry/configserver.json` controls which destinations are allowed for filesystem operations:

```json
{
  "systemd": {
    "shairport": "all",
    "raat": "all",
    "mpd": "all",
    "squeezelite": "all",
    "librespot": "all"
  },
  "filesystem": {
    "allowed_symlink_destinations": [
      "/var/lib/mpd/music/"
    ]
  }
}
```

**Filesystem Configuration:**
- `allowed_symlink_destinations`: Array of directory paths where symlink operations are permitted
- Without this configuration, no filesystem operations are allowed
- Directory paths should end with `/` for clarity

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

*HiFiBerry Configuration API v2.1.0*
