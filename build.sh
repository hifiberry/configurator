#!/bin/bash

cd `dirname $0`
MYDIR=$(pwd)

# Define variables
PACKAGE_NAME="configurator"
# Read version from setup.py instead of hardcoding it
VERSION=$(grep -oP "version=\"\K[^\"]+" setup.py)
OUTPUT_DIR="$MYDIR/out"
if [! -d "$OUTPUT_DIR"]; then
    mkdir -p "$OUTPUT_DIR"
fi
BUILD_DIR="deb_dist"
PACKAGEFILE="./PACKAGEFILE" # File to store the package name

# Function to clean up build files
clean() {
    echo "Cleaning up build files..."
    rm -rf "$BUILD_DIR"
    rm -rf "$PACKAGE_NAME.egg-info"
    rm -rf build
    rm -rf dist
    rm -f "$PACKAGEFILE"
    rm -rf $PACKAGE_NAME*.tar.gz
    echo "Cleanup completed."
}

# Function to build the package
build_package() {
    echo "Building the Debian package (version: $VERSION)..."
    python3 setup.py --command-packages=stdeb.command bdist_deb

    if [ ! -d "$BUILD_DIR" ]; then
        echo "Build failed. Exiting."
        exit 1
    fi

    # Create output directory if it doesn't exist
    mkdir -p "$OUTPUT_DIR"

    # Find and copy the built package
    echo "find "$BUILD_DIR" -name "${PACKAGE_NAME}_*.deb" ! -name "*dbgsym*" | head -n 1"
    DEB_PACKAGE=$(find "$BUILD_DIR" -name "python*${PACKAGE_NAME}_*.deb" ! -name "*dbgsym*" | head -n 1)
    echo $DEB_PACKAGE

    if [ -n "$DEB_PACKAGE" ]; then
        cp "$DEB_PACKAGE" "$OUTPUT_DIR"
        echo "$(basename "$DEB_PACKAGE")" > "$PACKAGEFILE"
        echo "Build completed. Package copied to $OUTPUT_DIR."
    else
        echo "Failed to find the .deb package to copy."
        exit 1
    fi
}

# Check script options
if [ "$1" == "--clean" ]; then
    clean
    exit 0
fi

# Default behavior: Build the package
clean
build_package
clean
