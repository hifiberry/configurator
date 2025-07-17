#!/bin/bash
set -e

cd `dirname $0`

# Extract version from changelog as single source of truth
CHANGELOG_VERSION=$(head -1 debian/changelog | sed 's/.*(\([^)]*\)).*/\1/')
echo "Using version from changelog: $CHANGELOG_VERSION"

# Check if DIST is set by environment variable
if [ -n "$DIST" ]; then
    echo "Using distribution from DIST environment variable: $DIST"
    DIST_ARG="--dist=$DIST"
else
    echo "No DIST environment variable set, using sbuild default"
    DIST_ARG=""
fi

sbuild \
    --chroot-mode=unshare \
    --no-clean-source \
    --enable-network \
    $DIST_ARG \
    --verbose

