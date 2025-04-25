#!/bin/bash
set -e

cd `dirname $0`
MYDIR=$(pwd)

# Define variables
PACKAGE_NAME="configurator"
VERSION=$(grep -oP "version=\"\K[^\"]+" setup.py)
OUTPUT_DIR="$MYDIR/out"
mkdir -p "$OUTPUT_DIR"
PACKAGEFILE="./PACKAGEFILE" # File to store the package name

# Function to clean up build files
clean() {
    echo "Cleaning up build files..."
    rm -rf build
    rm -rf deb_dist
    rm -rf "$PACKAGE_NAME.egg-info"
    rm -rf dist
    rm -f "$PACKAGEFILE"
    rm -rf "$PACKAGE_NAME"*.tar.gz
    echo "Cleanup completed."
}

# Function to build the package
build_package() {
    echo "Building the Debian package (version: $VERSION)..."
    
    # Create a manifest that includes systemd files and requirements.txt
    echo "include requirements.txt" > MANIFEST.in
    echo "include systemd/volume-store.service" >> MANIFEST.in
    echo "include systemd/volume-store.timer" >> MANIFEST.in
    
    # Copy the systemd files to the output dir as well
    mkdir -p "$OUTPUT_DIR/systemd"
    cp systemd/volume-store.service "$OUTPUT_DIR/systemd/"
    cp systemd/volume-store.timer "$OUTPUT_DIR/systemd/"
    
    # Build the package using stdeb
    python3 setup.py --command-packages=stdeb.command bdist_deb
    
    # Find the built package
    DEB_PACKAGE=$(find deb_dist -name "python3-$PACKAGE_NAME*.deb" | head -n 1)
    
    if [ -n "$DEB_PACKAGE" ]; then
        # Copy the package to the output directory
        cp "$DEB_PACKAGE" "$OUTPUT_DIR/"
        FINAL_DEB="$OUTPUT_DIR/$(basename "$DEB_PACKAGE")"
        echo "$(basename "$FINAL_DEB")" > "$PACKAGEFILE"
        
        # Now let's add our postinst script to activate the timer
        echo "Adding postinst script to enable timer during installation..."
        
        # Create a temporary directory
        TEMP_DIR=$(mktemp -d)
        echo "Using temporary directory: $TEMP_DIR"
        
        # Create a new structure for the modified package
        CONTENT_DIR="$TEMP_DIR/content"
        mkdir -p "$CONTENT_DIR"
        
        # Extract the original package
        dpkg-deb -R "$FINAL_DEB" "$CONTENT_DIR"
        
        # Ensure the DEBIAN directory exists and is writable
        mkdir -p "$CONTENT_DIR/DEBIAN"

        # Create the postinst script directly in the package
        cat > "$CONTENT_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/sh
# postinst script for python3-configurator

set -e

case "$1" in
    configure)
        echo "Enabling volume-store timer service..."
        systemctl daemon-reload || true
        systemctl enable volume-store.timer || true
        systemctl start volume-store.timer || true

        # Activate sambamount service during installation
        systemctl daemon-reload || true
        systemctl enable sambamount.service || true
        systemctl start sambamount.service || true
    ;;

    abort-upgrade|abort-remove|abort-deconfigure)
    ;;

    *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac

exit 0
EOF
        chmod 755 "$CONTENT_DIR/DEBIAN/postinst"

        # Copy sambamount.service to the package directory
        cp systemd/sambamount.service "$CONTENT_DIR/usr/lib/systemd/system/"
        chmod 644 "$CONTENT_DIR/usr/lib/systemd/system/sambamount.service"

        # Verify the script content
        echo "Verifying postinst script content:"
        cat "$CONTENT_DIR/DEBIAN/postinst"

        # Build the modified package
        MODIFIED_DEB="$OUTPUT_DIR/python3-configurator_${VERSION}-1_all.deb"
        dpkg-deb --build "$CONTENT_DIR" "$MODIFIED_DEB"

        echo "Build completed. Package saved as: $(basename "$MODIFIED_DEB")"
        echo "$(basename "$MODIFIED_DEB")" > "$PACKAGEFILE"

        # Verify the package control information
        if dpkg-deb -I "$MODIFIED_DEB" | grep -q postinst; then
            echo "SUCCESS: postinst script is included in the package."
        else
            echo "ERROR: postinst script is not included in the package."
            exit 1
        fi

        # Clean up
        rm -rf "$TEMP_DIR"
    else
        echo "Failed to find the .deb package."
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

echo
echo "To test the package installation and timer activation:"
echo "sudo dpkg -i $OUTPUT_DIR/$(cat "$PACKAGEFILE")"
