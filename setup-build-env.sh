#!/bin/bash
# Setup script for Debian Trixie dh_virtualenv build environment
# Installs all necessary build tools and dependencies

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== HiFiBerry Configurator Build Environment Setup ===${NC}"
echo "This script will install all required tools for Debian Trixie packaging"
echo

# Check if running as root for apt commands
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${YELLOW}Some commands require sudo. You may be prompted for your password.${NC}"
        return 1
    fi
    return 0
}

# Detect Debian version
detect_debian() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DEBIAN_VERSION=$VERSION_CODENAME
        echo -e "${GREEN}Detected Debian version: ${DEBIAN_VERSION}${NC}"
        
        if [ "$DEBIAN_VERSION" != "trixie" ] && [ "$DEBIAN_VERSION" != "bookworm" ] && [ "$DEBIAN_VERSION" != "bullseye" ]; then
            echo -e "${YELLOW}Warning: Not running Trixie. Package may require adjustments.${NC}"
        fi
    else
        echo -e "${RED}Could not detect Debian version${NC}"
        return 1
    fi
}

# Install build tools
install_build_tools() {
    echo
    echo -e "${YELLOW}Installing core build tools...${NC}"
    
    BUILD_TOOLS=(
        "build-essential"      # gcc, make, etc.
        "debhelper"            # Debian package helpers
        "dh-virtualenv"        # Python virtualenv packager
        "git"                  # Version control (often needed)
        "apt-utils"            # APT utilities
    )
    
    for tool in "${BUILD_TOOLS[@]}"; do
        if ! dpkg -l | grep -q "^ii.*${tool}"; then
            echo "  Installing ${tool}..."
            sudo apt-get install -y "$tool" > /dev/null 2>&1 || {
                echo -e "${RED}  Failed to install ${tool}${NC}"
                return 1
            }
        else
            echo -e "  ✓ ${tool} already installed"
        fi
    done
    
    echo -e "${GREEN}✓ Build tools installed${NC}"
}

# Install Python development headers
install_python_dev() {
    echo
    echo -e "${YELLOW}Installing Python development tools...${NC}"
    
    PYTHON_TOOLS=(
        "python3"              # Python 3 interpreter
        "python3-dev"          # Python 3 development headers
        "python3-pip"          # Package installer
        "python3-setuptools"   # Package setup tools
        "python3-wheel"        # Wheel package format
        "python3-venv"         # Virtual environments
    )
    
    for tool in "${PYTHON_TOOLS[@]}"; do
        if ! dpkg -l | grep -q "^ii.*${tool}"; then
            echo "  Installing ${tool}..."
            sudo apt-get install -y "$tool" > /dev/null 2>&1 || {
                echo -e "${RED}  Failed to install ${tool}${NC}"
                return 1
            }
        else
            echo -e "  ✓ ${tool} already installed"
        fi
    done
    
    echo -e "${GREEN}✓ Python tools installed${NC}"
}

# Install system libraries
install_system_libs() {
    echo
    echo -e "${YELLOW}Installing system libraries...${NC}"
    
    SYSTEM_LIBS=(
        "pkg-config"           # Package configuration utility
        "libffi-dev"           # Foreign function interface library
        "libssl-dev"           # SSL/TLS development headers
        "i2c-tools"            # I2C hardware tools
        "fakeroot"             # Fake root for package building
    )
    
    for lib in "${SYSTEM_LIBS[@]}"; do
        if ! dpkg -l | grep -q "^ii.*${lib}"; then
            echo "  Installing ${lib}..."
            sudo apt-get install -y "$lib" > /dev/null 2>&1 || {
                echo -e "${RED}  Failed to install ${lib}${NC}"
                return 1
            }
        else
            echo -e "  ✓ ${lib} already installed"
        fi
    done
    
    echo -e "${GREEN}✓ System libraries installed${NC}"
}

# Install optional but recommended tools
install_optional() {
    echo
    echo -e "${YELLOW}Installing optional tools...${NC}"
    
    OPTIONAL=(
        "sbuild"               # Isolated build environment
        "ccache"               # Compiler cache
        "devscripts"           # Debian development scripts
        "lintian"              # Package checker
    )
    
    for tool in "${OPTIONAL[@]}"; do
        if ! dpkg -l | grep -q "^ii.*${tool}"; then
            echo "  (Optional) Installing ${tool}..."
            sudo apt-get install -y "$tool" 2>/dev/null || {
                echo -e "${YELLOW}  Skipping ${tool} (not critical)${NC}"
            }
        else
            echo -e "  ✓ ${tool} already installed"
        fi
    done
}

# Update package lists
update_apt() {
    echo
    echo -e "${YELLOW}Updating package lists...${NC}"
    sudo apt-get update > /dev/null 2>&1 || {
        echo -e "${RED}Failed to update package lists${NC}"
        return 1
    }
    echo -e "${GREEN}✓ Package lists updated${NC}"
}

# Verify installation
verify_installation() {
    echo
    echo -e "${YELLOW}Verifying installation...${NC}"
    
    COMMANDS=(
        "dpkg-buildpackage"
        "dh_virtualenv"
        "python3"
        "pip3"
        "pkg-config"
        "fakeroot"
    )
    
    local all_ok=true
    for cmd in "${COMMANDS[@]}"; do
        if command -v "$cmd" &> /dev/null; then
            VERSION=$("$cmd" --version 2>&1 | head -1)
            echo -e "  ✓ ${GREEN}${cmd}${NC}: ${VERSION}"
        else
            echo -e "  ✗ ${RED}${cmd} not found${NC}"
            all_ok=false
        fi
    done
    
    if [ "$all_ok" = true ]; then
        echo -e "${GREEN}✓ All tools verified${NC}"
        return 0
    else
        echo -e "${RED}✗ Some tools not found${NC}"
        return 1
    fi
}

# Show summary
show_summary() {
    echo
    echo -e "${GREEN}=== Setup Complete ===${NC}"
    echo
    echo "Your build environment is ready for Debian Trixie packaging."
    echo
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Navigate to project: cd /home/ulf/data/configurator"
    echo "2. Build package: DIST=trixie ./build-deb.sh"
    echo "3. Check output: ls ../*.deb"
    echo
    echo -e "${BLUE}Documentation:${NC}"
    echo "  • DEBIAN_BUILD.md - Comprehensive build guide"
    echo "  • DEBIAN_TRIXIE_CONFIG.md - Configuration summary"
    echo "  • build-deb-trixie.sh - Automated build script"
    echo
    echo -e "${BLUE}Useful commands:${NC}"
    echo "  dpkg-checkbuilddeps   - Check build dependencies"
    echo "  dpkg-buildpackage     - Build Debian package"
    echo "  dpkg -c *.deb         - List package contents"
    echo
}

# Main execution
main() {
    detect_debian || exit 1
    update_apt || exit 1
    install_build_tools || exit 1
    install_python_dev || exit 1
    install_system_libs || exit 1
    install_optional
    verify_installation || exit 1
    show_summary
}

# Run main function
main
