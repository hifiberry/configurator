#!/bin/bash
set -e

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SOURCE_DIR="${SCRIPT_DIR}"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"

# Define variables
PACKAGE_NAME="configurator"
VERSION=$(grep -oP "version=\"\K[^\"]+" "${SOURCE_DIR}/setup.py")
DOCKER_TAG="configurator-build-env"
DOCKER_DIR="${PARENT_DIR}/configurator-docker-build"
OUTPUT_DIR="${PARENT_DIR}/out"

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

# Function to clean up build files
clean() {
    echo "Cleaning up build files..."
    rm -rf "${SOURCE_DIR}/build"
    rm -rf "${SOURCE_DIR}/deb_dist"
    rm -rf "${SOURCE_DIR}/${PACKAGE_NAME}.egg-info"
    rm -rf "${SOURCE_DIR}/dist"
    rm -rf "${SOURCE_DIR}/${PACKAGE_NAME}*.tar.gz"
    echo "Cleanup completed."
}

# Function to ensure Docker image exists or build it
ensure_docker_image() {
    echo "Checking for Docker image ${DOCKER_TAG}..."
    if ! docker image inspect "${DOCKER_TAG}" &> /dev/null; then
        echo "Docker image not found. Building Docker image: ${DOCKER_TAG}..."
        # Ensure Docker directory exists
        mkdir -p "${DOCKER_DIR}"
        
        # Build the Docker image
        docker build -t "${DOCKER_TAG}" -f "${DOCKER_DIR}/Dockerfile" "${DOCKER_DIR}"
        echo "Docker image build completed."
    else
        echo "Docker image ${DOCKER_TAG} already exists."
    fi
}

# Function to build the Debian package
build_package() {
    echo "Building the Debian package (version: ${VERSION}) using Docker..."
    
    # Ensure Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "Error: Docker is not running or not accessible."
        exit 1
    fi
    
    # Ensure Docker image exists
    ensure_docker_image
    
    # Set Docker paths
    DOCKER_SCRIPT_DIR="${SOURCE_DIR}"
    DOCKER_OUTPUT_DIR="${OUTPUT_DIR}"
    
    # For Windows, we need to convert paths for Docker if necessary
    if [[ "${OSTYPE}" == "msys" || "${OSTYPE}" == "cygwin" || "${OSTYPE}" == "win32" ]]; then
        echo "Windows detected, converting paths for Docker..."
        
        # Convert Windows-style paths to Docker paths
        DOCKER_SCRIPT_DIR=$(echo "${SOURCE_DIR}" | sed 's|\\|/|g' | sed 's|^C:|/c|i')
        DOCKER_OUTPUT_DIR=$(echo "${OUTPUT_DIR}" | sed 's|\\|/|g' | sed 's|^C:|/c|i')
    fi
    
    echo "Using Docker mount paths:"
    echo "  Source: ${DOCKER_SCRIPT_DIR}"
    echo "  Output: ${DOCKER_OUTPUT_DIR}"
    
    # Get current user ID and group ID for file ownership
    HOST_USER_ID=$(id -u)
    HOST_GROUP_ID=$(id -g)
    echo "Building as user ID: ${HOST_USER_ID}, group ID: ${HOST_GROUP_ID}"
    
    # Create the init script for Docker
    echo "Creating initialization script for Docker..."
    INIT_SCRIPT=$(mktemp)
    
    # Write the initialization script
    cat > "${INIT_SCRIPT}" << 'EOF'
#!/bin/bash
# Configure non-root user to have sudo access without password
echo "build_user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/build_user
chmod 0440 /etc/sudoers.d/build_user

# Make sure our user can sudo without tty
echo "Defaults !requiretty" >> /etc/sudoers

# Create the compile script
cat > /tmp/compile.sh << 'END_COMPILE_SCRIPT'
#!/bin/bash
set -e

echo "Starting package build..."

# Set environment variables
export USER=root
export LOGNAME=root
export DEBFULLNAME="HiFiBerry"
export DEBEMAIL="info@hifiberry.com"

# Get the package version from environment variable
PACKAGE_VERSION="${PACKAGE_VERSION:-1.0.0}"
echo "Building version: ${PACKAGE_VERSION}"

# Set directories
BUILD_DIR="${BUILD_DIR:-/build}"
OUT_DIR="${OUT_DIR:-/out}"

echo "Working directory: $(pwd)"
echo "Build directory: ${BUILD_DIR}"
echo "Output directory: ${OUT_DIR}"

# List contents to verify
echo "Listing build directory contents:"
ls -la "${BUILD_DIR}"

# Create the manifest file
echo "Creating MANIFEST.in..."
cat > ${BUILD_DIR}/MANIFEST.in << EOFMANIFEST
include requirements.txt
include systemd/volume-store.service
include systemd/volume-store.timer
include systemd/sambamount.service
EOFMANIFEST

# Build the package using stdeb
cd ${BUILD_DIR}
python3 setup.py --command-packages=stdeb.command bdist_deb

# Find the built package
DEB_PACKAGE=$(find deb_dist -name "python3-configurator*.deb" | head -n 1)

if [ -n "$DEB_PACKAGE" ]; then
    # Use a temporary directory that we know we have permissions for
    TEMP_DIR="/tmp/build-dir/$(date +%s)"
    CONTENT_DIR="${TEMP_DIR}/content"
    mkdir -p "${CONTENT_DIR}"
    # Ensure we have the right permissions
    chmod -R 755 "${TEMP_DIR}"
    
    # Extract the original package
    dpkg-deb -R "${DEB_PACKAGE}" "${CONTENT_DIR}"
    
    # Ensure the DEBIAN directory exists
    mkdir -p "${CONTENT_DIR}/DEBIAN"

    # Ensure the directory has the right permissions
    chmod -R 755 "${CONTENT_DIR}/DEBIAN"
    
    # Create the postinst script
    cat > "${CONTENT_DIR}/DEBIAN/postinst" << 'EOFS'
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
EOFS
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
    if grep -q "postinst" "${FINAL_DEB}" || dpkg-deb --info "${FINAL_DEB}" | grep -q postinst 2>/dev/null; then
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
END_COMPILE_SCRIPT

chmod +x /tmp/compile.sh
EOF
    
    chmod +x "${INIT_SCRIPT}"
    
    # Run the Docker container to build the package
    echo "Running Docker container to build the package..."
    docker run --rm \
        --mount type=bind,source="${DOCKER_SCRIPT_DIR}",target=/build \
        --mount type=bind,source="${DOCKER_OUTPUT_DIR}",target=/out \
        --mount type=bind,source="${INIT_SCRIPT}",target=/init.sh \
        -e PACKAGE_VERSION="${VERSION}" \
        -e BUILD_DIR="/build" \
        -e OUT_DIR="/out" \
        -w /build \
        "${DOCKER_TAG}" bash -c "chmod +x /init.sh && /init.sh && adduser --disabled-password --gecos '' --uid ${HOST_USER_ID} build_user 2>/dev/null || true && chown -R build_user:build_user /build /out /tmp && su build_user -c 'cd /build && bash /tmp/compile.sh'"
    
    # Clean up the init script
    rm -f "${INIT_SCRIPT}"
    
    echo "Package build completed. Output saved to ${OUTPUT_DIR}/python3-configurator_${VERSION}-1_all.deb"
}

# Parse command line arguments
case "$1" in
    clean)
        clean
        ;;
    *)
        # Default action is to build the package
        build_package
        ;;
esac

exit 0