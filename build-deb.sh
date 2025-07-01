#!/bin/bash
set -e

cd `dirname $0`

# Expected version
EXPECTED_VERSION="1.6.5"

# Check if the changelog version matches the expected version
CHANGELOG_VERSION=$(head -1 debian/changelog | sed 's/.*(\([^)]*\)).*/\1/')
if [ "$CHANGELOG_VERSION" != "$EXPECTED_VERSION" ]; then
    echo "ERROR: Changelog version ($CHANGELOG_VERSION) does not match expected version ($EXPECTED_VERSION)"
    echo "Please update debian/changelog manually"
    exit 1
fi

# Check if setup.py version matches
SETUP_VERSION=$(grep 'version=' setup.py | sed 's/.*version="\([^"]*\)".*/\1/')
if [ "$SETUP_VERSION" != "$EXPECTED_VERSION" ]; then
    echo "ERROR: setup.py version ($SETUP_VERSION) does not match expected version ($EXPECTED_VERSION)"
    echo "Please update setup.py manually"
    exit 1
fi

echo "Version consistency check passed: $EXPECTED_VERSION"

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

