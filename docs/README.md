# HiFiBerry Configuration API Documentation

This directory contains the HTML documentation for the HiFiBerry Configuration API.

## Files

- `api-documentation.html` - Main HTML documentation served by the API server

## Maintaining the Documentation

The HTML documentation is served directly from the `api-documentation.html` file. To update the documentation:

1. Edit the `api-documentation.html` file directly
2. The server will automatically serve the updated documentation
3. The file is copied to `/usr/share/doc/hifiberry-configurator/` during package installation

## Dynamic Content

The server automatically replaces `localhost:1081` with the actual server host and port when serving the documentation. This ensures the examples in the documentation always show the correct server address.

## File Locations

The server looks for the documentation file in these locations (in order):
1. `docs/api-documentation.html` (relative to the server script - for development)
2. `/usr/share/doc/hifiberry-configurator/api-documentation.html` (system installation)

If neither file is found, the server will serve a simple fallback page with a link to the OpenAPI specification.

## Version Updates

When updating the API version, remember to update:
- The version number in the HTML title and navigation
- Any version-specific information in the content
- The version in the server.py file should match
