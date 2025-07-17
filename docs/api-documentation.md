# HiFiBerry Configuration API Documentation

**Version 1.7.0**

- [Endpoints](#endpoints)
- [Examples](#examples)
- [Error Codes](#error-codes)
- [OpenAPI Spec](/api/v1/openapi.json)

## Overview

The HiFiBerry Configuration API provides REST endpoints for managing configuration settings in the HiFiBerry system. All responses are in JSON format with consistent structure.

**Base URL:** `http://localhost:1081`

> **Note:** Replace localhost:1081 with your actual server address and port.

## Endpoints

### `GET /version`

Get version information and available endpoints.

**Response:**
```json
{"service": "hifiberry-config-api", "version": "1.7.0", "api_version": "v1", "description": "HiFiBerry Configuration Server", "endpoints": {"version": "/version", "config": "/api/v1/config", "docs": "/docs", "openapi": "/api/v1/openapi.json"}}
```

### `GET /api/v1/config`

Get all configuration key-value pairs.

**Parameters:**
- **prefix** (query, optional): Filter keys by prefix

**Response:**
```json
{"status": "success", "data": {"volume": "75", "soundcard": "hifiberry-dac"}, "count": 2}
```

### `GET /api/v1/config/keys`

Get all configuration keys only (without values).

**Parameters:**
- **prefix** (query, optional): Filter keys by prefix

**Response:**
```json
{"status": "success", "data": ["volume", "soundcard"], "count": 2}
```

### `GET /api/v1/config/key/{key}`

Get a specific configuration value by key.

**Parameters:**
- **key** (path, required): Configuration key name
- **secure** (query, optional): Set to "true" for secure/encrypted values
- **default** (query, optional): Default value if key not found

**Response:**
```json
{"status": "success", "data": {"key": "volume", "value": "75"}}
```

### `POST` / `PUT /api/v1/config/key/{key}`

Set or update a configuration value.

**Parameters:**
- **key** (path, required): Configuration key name
- **Content-Type** (header, required): application/json

**Request Body:**
- **value** (required): The value to set
- **secure** (optional): Store as encrypted value

**Request Body Example:**
```json
{"value": "75", "secure": false}
```

**Response:**
```json
{"status": "success", "message": "Configuration key \"volume\" set successfully", "data": {"key": "volume", "value": "75"}}
```

### `DELETE /api/v1/config/key/{key}`

Delete a configuration key and its value.

**Parameters:**
- **key** (path, required): Configuration key name

**Response:**
```json
{"status": "success", "message": "Configuration key \"volume\" deleted successfully"}
```

## Examples

### curl Commands

**Get version information:**
```bash
curl http://localhost:1081/version
```

**Get all configuration:**
```bash
curl http://localhost:1081/api/v1/config
```

**Get specific value:**
```bash
curl http://localhost:1081/api/v1/config/key/volume
```

**Set configuration value:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"value":"75"}' \
     http://localhost:1081/api/v1/config/key/volume
```

**Set secure value:**
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"value":"secret","secure":true}' \
     http://localhost:1081/api/v1/config/key/password
```

**Delete configuration:**
```bash
curl -X DELETE http://localhost:1081/api/v1/config/key/volume
```

## Error Responses

| HTTP Code | Description | Example Response |
|-----------|-------------|------------------|
| 400 | Bad Request | `{"status": "error", "message": "Missing required field: value"}` |
| 404 | Not Found | `{"status": "error", "message": "Configuration key not found"}` |
| 500 | Internal Server Error | `{"status": "error", "message": "Failed to retrieve configuration data"}` |

## Additional Resources

- [OpenAPI 3.0 Specification](/api/v1/openapi.json) - Machine-readable API specification

---

*HiFiBerry Configuration API v1.7.0 | [Contact Support](mailto:info@hifiberry.com)*
