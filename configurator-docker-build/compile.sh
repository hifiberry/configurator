#!/bin/bash
set -e

echo "Starting configurator package build (Version: ${PACKAGE_VERSION})..."

# Environment variables
export USER=root
export LOGNAME=root
export DEBFULLNAME="HiFiBerry"
export DEBEMAIL="info@hifiberry.com"

echo "Working directory: $(pwd)"
echo "Build directory: ${BUILD_DIR}"
echo "Output directory: ${OUT_DIR}"

# List contents to verify
echo "Listing build directory contents:"
ls -la "${BUILD_DIR}"

# Create the manifest file
echo "Creating MANIFEST.in..."
cat > ${BUILD_DIR}/MANIFEST.in << EOF
include requirements.txt
include systemd/volume-store.service
include systemd/volume-store.timer
include systemd/sambamount.service
EOF

# Copy the sources to build directory
echo "Building the package..."

# Build the package using stdeb
cd ${BUILD_DIR}
python3 setup.py --command-packages=stdeb.command bdist_deb

# Find the built package
DEB_PACKAGE=$(find deb_dist -name "python3-configurator*.deb" | head -n 1)

if [ -n "$DEB_PACKAGE" ]; then
    # Copy the package to a temporary directory for modification
    TEMP_DIR=$(mktemp -d)
    CONTENT_DIR="${TEMP_DIR}/content"
    mkdir -p "${CONTENT_DIR}"
    
    # Extract the original package
    dpkg-deb -R "${DEB_PACKAGE}" "${CONTENT_DIR}"
    
    # Ensure the DEBIAN directory exists
    mkdir -p "${CONTENT_DIR}/DEBIAN"

    # Create the postinst script
    cat > "${CONTENT_DIR}/DEBIAN/postinst" << 'EOF'
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
    chmod 755 "${CONTENT_DIR}/DEBIAN/postinst"

    # Ensure the systemd directory exists
    mkdir -p "${CONTENT_DIR}/usr/lib/systemd/system/"
    
    # Copy sambamount.service to the package
    cp ${BUILD_DIR}/systemd/sambamount.service "${CONTENT_DIR}/usr/lib/systemd/system/"
    chmod 644 "${CONTENT_DIR}/usr/lib/systemd/system/sambamount.service"

    # Build the modified package
    FINAL_DEB="${OUT_DIR}/python3-configurator_${PACKAGE_VERSION}-1_all.deb"
    dpkg-deb --build "${CONTENT_DIR}" "${FINAL_DEB}"
    
    echo "Package build completed successfully: $(basename ${FINAL_DEB})"
    
    # Verify the package includes the postinst script
    if dpkg-deb -I "${FINAL_DEB}" | grep -q postinst; then
        echo "SUCCESS: postinst script is included in the package."
    else
        echo "ERROR: postinst script is not included in the package."
        exit 1
    fi
    
    # Clean up
    rm -rf "${TEMP_DIR}"
else
    echo "Failed to find the .deb package."
    exit 1
fi
