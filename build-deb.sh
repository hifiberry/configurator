#!/bin/bash
set -e

cd `dirname $0`

# Extract version from changelog as single source of truth
CHANGELOG_VERSION=$(head -1 debian/changelog | sed 's/.*(\([^)]*\)).*/\1/')
echo "Version from changelog: $CHANGELOG_VERSION"

# Check if setup.py version matches changelog
SETUP_VERSION=$(grep 'version=' setup.py | sed 's/.*version="\([^"]*\)".*/\1/')
if [ "$SETUP_VERSION" != "$CHANGELOG_VERSION" ]; then
    echo "ERROR: setup.py version ($SETUP_VERSION) does not match changelog version ($CHANGELOG_VERSION)"
    echo "Please update setup.py to match changelog version"
    exit 1
fi

echo "Version consistency check passed: $CHANGELOG_VERSION"

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

