# HiFiBerry Configuration API Documentation

This directory contains the documentation for the HiFiBerry Configuration API.

## Files

- `api-documentation.md` - Main Markdown documentation served by the API server
- `api-documentation.html` - Legacy HTML documentation (deprecated)

## Maintaining the Documentation

The documentation is maintained in Markdown format in the `api-documentation.md` file. The server automatically converts this to HTML when serving to browsers.

To update the documentation:

1. Edit the `api-documentation.md` file directly
2. The server will automatically serve the updated documentation as HTML or Markdown based on the request
3. The file is copied to `/usr/share/doc/hifiberry-configurator/` during package installation

## Documentation Formats

The server can serve the documentation in multiple formats:

- **HTML**: Accessed via browser at `/` or `/docs` (automatic conversion from Markdown)
- **Markdown**: Accessed via `/docs.md` or by setting Accept header to `text/markdown`
- **JSON**: Accessed by setting Accept header to `application/json`

## Dynamic Content

The server automatically replaces `localhost:1081` with the actual server host and port when serving the documentation. This ensures the examples in the documentation always show the correct server address.

## File Locations

The server looks for the documentation file in these locations (in order):
1. `docs/api-documentation.md` (relative to the server script - for development)
2. `/usr/share/doc/hifiberry-configurator/api-documentation.md` (system installation)

If neither file is found, the server will serve a simple fallback page with a link to the OpenAPI specification.

## Version Updates

When updating the API version, remember to update:
- The version number in the Markdown title and content
- Any version-specific information in the content
- The version in the server.py file should match
