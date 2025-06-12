#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}"

# Define variables
PACKAGE_NAME="configurator"
VERSION=$(grep -oP "version=\"\K[^\"]+" setup.py)
DOCKER_TAG="configurator-build-env"
DOCKER_DIR="${SCRIPT_DIR}/configurator-docker-build"
OUTPUT_DIR="${SCRIPT_DIR}/out"
mkdir -p "${OUTPUT_DIR}"
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

# Function to build the Docker image
build_docker_image() {
    echo "Building Docker image: ${DOCKER_TAG}..."
    
    # Fix line endings in the compile.sh script
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        echo "Windows detected, fixing line endings in compile.sh..."
        if command -v dos2unix &> /dev/null; then
            dos2unix "${DOCKER_DIR}/compile.sh" || true
        else
            # Use perl as an alternative to dos2unix
            perl -pi -e 's/\r$//' "${DOCKER_DIR}/compile.sh" || true
        fi
    fi
    
    # Make sure compile.sh is executable
    chmod +x "${DOCKER_DIR}/compile.sh" || true
    
    # Build the Docker image
    docker build -t "${DOCKER_TAG}" -f "${DOCKER_DIR}/Dockerfile" "${DOCKER_DIR}"
    echo "Docker image build completed."
}

# Function to build the package
build_package() {
    echo "Building the Debian package (version: ${VERSION}) using Docker..."
    
    # Ensure Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "Error: Docker is not running or not accessible."
        exit 1
    fi
    
    # Build or update the Docker image
    build_docker_image

    # Copy the systemd files to the output dir 
    mkdir -p "${OUTPUT_DIR}/systemd"
    cp systemd/volume-store.service "${OUTPUT_DIR}/systemd/"
    cp systemd/volume-store.timer "${OUTPUT_DIR}/systemd/"
    cp systemd/sambamount.service "${OUTPUT_DIR}/systemd/"
    
    # Set Docker paths
    DOCKER_SCRIPT_DIR="${SCRIPT_DIR}"
    DOCKER_OUTPUT_DIR="${OUTPUT_DIR}"
    
    # For Windows, we need to convert paths for Docker if necessary
    if [[ "${OSTYPE}" == "msys" || "${OSTYPE}" == "cygwin" || "${OSTYPE}" == "win32" ]]; then
        echo "Windows detected, converting paths for Docker..."
        
        # Convert Windows-style paths to Docker paths if needed
        DOCKER_SCRIPT_DIR=$(echo "${SCRIPT_DIR}" | sed 's|\\|/|g' | sed 's|^C:|/c|i')
        DOCKER_OUTPUT_DIR=$(echo "${OUTPUT_DIR}" | sed 's|\\|/|g' | sed 's|^C:|/c|i')
    fi
    
    echo "Using Docker mount paths:"
    echo "  Source: ${DOCKER_SCRIPT_DIR}"
    echo "  Output: ${DOCKER_OUTPUT_DIR}"
    
    # Get current user ID and group ID for file ownership
    HOST_USER_ID=$(id -u)
    HOST_GROUP_ID=$(id -g)
    echo "Building as user ID: ${HOST_USER_ID}, group ID: ${HOST_GROUP_ID}"
    
    # Run the Docker container to build the package and generate compile script on the fly
    # Use the same user ID as the host to avoid permission issues
    docker run --rm \
        --user ${HOST_USER_ID}:${HOST_GROUP_ID} \
        --mount type=bind,source="${DOCKER_SCRIPT_DIR}",target=/build \
        --mount type=bind,source="${DOCKER_OUTPUT_DIR}",target=/out \
        -e PACKAGE_VERSION="${VERSION}" \
        "${DOCKER_TAG}" bash -c "cat > /tmp/compile.sh << 'EOL'
#!/bin/bash
set -e

echo \"Starting configurator package build (Version: \${PACKAGE_VERSION})...\"

# Environment variables
export USER=root
export LOGNAME=root
export DEBFULLNAME=\"HiFiBerry\"
export DEBEMAIL=\"info@hifiberry.com\"

echo \"Working directory: \$(pwd)\"
echo \"Build directory: \${BUILD_DIR}\"
echo \"Output directory: \${OUT_DIR}\"

# List contents to verify
echo \"Listing build directory contents:\"
ls -la \"\${BUILD_DIR}\"

# Create the manifest file
echo \"Creating MANIFEST.in...\"
cat > \${BUILD_DIR}/MANIFEST.in << EOF
include requirements.txt
include systemd/volume-store.service
include systemd/volume-store.timer
include systemd/sambamount.service
EOF

# Build the package using stdeb
cd \${BUILD_DIR}
python3 setup.py --command-packages=stdeb.command bdist_deb

# Find the built package
DEB_PACKAGE=\$(find deb_dist -name \"python3-configurator*.deb\" | head -n 1)

if [ -n \"\$DEB_PACKAGE\" ]; then
    # Use a temporary directory that we know we have permissions for
    TEMP_DIR=\"/tmp/build-dir/\$(date +%s)\"
    CONTENT_DIR=\"\${TEMP_DIR}/content\"
    mkdir -p \"\${CONTENT_DIR}\"
    # Ensure we have the right permissions
    chmod -R 755 \"\${TEMP_DIR}\"
    
    # Extract the original package
    dpkg-deb -R \"\${DEB_PACKAGE}\" \"\${CONTENT_DIR}\"
    
    # Ensure the DEBIAN directory exists
    mkdir -p \"\${CONTENT_DIR}/DEBIAN\"

    # Ensure the directory has the right permissions
    chmod -R 755 \"\${CONTENT_DIR}/DEBIAN\"
    
    # Create the postinst script
    cat > \"\${CONTENT_DIR}/DEBIAN/postinst\" << 'EOFS'
#!/bin/sh
# postinst script for python3-configurator

set -e

case \"\$1\" in
    configure)
        echo \"Enabling volume-store timer service...\"
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
        echo \"postinst called with unknown argument \\\`\$1'\" >&2
        exit 1
    ;;
esac

exit 0
EOFS
    chmod 755 \"\${CONTENT_DIR}/DEBIAN/postinst\"

    # Ensure the systemd directory exists
    mkdir -p \"\${CONTENT_DIR}/usr/lib/systemd/system/\"
    
    # Copy sambamount.service to the package
    cp \${BUILD_DIR}/systemd/sambamount.service \"\${CONTENT_DIR}/usr/lib/systemd/system/\"
    chmod 644 \"\${CONTENT_DIR}/usr/lib/systemd/system/sambamount.service\"

    # Build the modified package
    FINAL_DEB=\"\${OUT_DIR}/python3-configurator_\${PACKAGE_VERSION}-1_all.deb\"
    dpkg-deb --build \"\${CONTENT_DIR}\" \"\${FINAL_DEB}\"
    
    echo \"Package build completed successfully: \$(basename \${FINAL_DEB})\"
    
    # Verify the package includes the postinst script
    if dpkg-deb -I \"\${FINAL_DEB}\" | grep -q postinst; then
        echo \"SUCCESS: postinst script is included in the package.\"
    else
        echo \"ERROR: postinst script is not included in the package.\"
        exit 1
    fi
    
    # Clean up
    rm -rf \"\${TEMP_DIR}\"
else
    echo \"Failed to find the .deb package.\"
    exit 1
fi
EOL
chmod +x /tmp/compile.sh && /tmp/compile.sh"
    
    # Find the package name
    FINAL_DEB=$(find "${OUTPUT_DIR}" -name "python3-configurator_${VERSION}*.deb" | head -n 1)
    
    if [ -n "${FINAL_DEB}" ]; then
        echo "Build completed. Package saved as: $(basename "${FINAL_DEB}")"
        echo "$(basename "${FINAL_DEB}")" > "${PACKAGEFILE}"
    else
        echo "Failed to find the .deb package."
        exit 1
    fi
}

# Process command-line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --clean)
            clean
            exit 0
            ;;
        --rebuild-docker)
            build_docker_image
            exit 0
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --clean         Clean build artifacts"
            echo "  --rebuild-docker  Rebuild the Docker image only"
            echo "  --help          Display this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $key"
            exit 1
            ;;
    esac
    shift
done

# Default behavior: Clean and build the package
clean
build_package

echo
echo "Build completed successfully!"
echo "To test the package installation:"
echo "sudo dpkg -i $OUTPUT_DIR/$(cat "$PACKAGEFILE" 2>/dev/null || echo "python3-configurator_${VERSION}-1_all.deb")"
