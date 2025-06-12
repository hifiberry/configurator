#!/bin/bash
set -e

# Default to root if not specified
USER_ID=${HOST_USER_ID:-0}
GROUP_ID=${HOST_GROUP_ID:-0}

# Function to handle permissions at end of operations
fix_permissions() {
  if [ "$USER_ID" != "0" ]; then
    echo "Fixing permissions for user $USER_ID:$GROUP_ID"
    chown -R $USER_ID:$GROUP_ID /out || true
    find /build -user root -not -path "*/\.*" -exec chown -R $USER_ID:$GROUP_ID {} \; 2>/dev/null || true
  fi
}

# Trap to ensure permissions are fixed even if the script fails
trap fix_permissions EXIT

# Execute the command passed to the entrypoint
exec "$@"
