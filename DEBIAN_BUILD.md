# HiFiBerry Configurator - Debian Trixie Build with dh_virtualenv

This document describes the Debian Trixie-conform build environment using `dh_virtualenv` for the hifiberry-configurator package.

## Overview

The package uses `dh_virtualenv` to create a self-contained Python virtual environment with all dependencies vendored into the Debian package. This approach provides:

- **Isolation**: All Python dependencies are isolated in a virtualenv
- **Reproducibility**: Consistent versions across all installations
- **Simplicity**: No need for users to manage Python dependencies separately
- **Compatibility**: Works on minimal systems without system Python packages

## Directory Structure

```
debian/
├── rules                           # Build rules for dh
├── control                         # Package metadata and dependencies
├── dirs                            # Directories to create
├── hifiberry-configurator.install  # Files to install
├── hifiberry-configurator.postinst # Post-install hook
├── hifiberry-configurator.prerm    # Pre-remove hook
├── source/
│   └── format                      # Debian source format
├── changelog                       # Package changelog
├── copyright                       # License information
├── .gitignore                      # Build artifacts to ignore
└── (other service/config files)
```

## Build Environment Setup

### Debian Trixie Requirements

The build requires the following tools and libraries:

```bash
# Core build tools
sudo apt install build-essential debhelper dh-virtualenv

# Python development headers
sudo apt install python3-dev python3-pip python3-setuptools python3-wheel

# Additional build dependencies
sudo apt install pkg-config libffi-dev libssl-dev i2c-tools
```

### Debian Package Specifications

- **Debhelper Compatibility**: 13 (compatible with Bullseye and newer)
- **Source Format**: 3.0 (quilt) - Modern Debian format with quilt patches support
- **Architecture**: `any` (architecture-independent binaries in virtualenv)
- **Build Dependencies**: Specified in `debian/control`

## Configuration Files

### debian/rules

The build rules file implements the dh_virtualenv workflow:

- **Sequencer**: `dh --with virtualenv --buildsystem=pybuild`
- **Override `dh_virtualenv`**: Configures virtualenv installation options
  - `--builtin-venv`: Use Python 3's built-in venv instead of virtualenv
  - `--install-suffix`: Sets virtualenv location to `/usr/lib/hifiberry-configurator`
  - `--python`: Uses system Python 3
  - `--requirements`: Installs from requirements.txt
  - `--extra-pip-arg`: Optimizations (no cache, compile bytecode)

### debian/control

Specifies package metadata and dependencies:

- **Build-Depends**: Tools needed during build phase
  - `debhelper-compat (= 13)`: Modern debhelper with compat level 13
  - `dh-virtualenv`: Provides dh_virtualenv sequencer
  - `python3-dev`, `python3-pip`, `python3-setuptools`: Python build tools
  - `python3-wheel`: For wheel package support
  - `libffi-dev`, `libssl-dev`: Needed by some dependencies (cryptography)
  - `i2c-tools`: Hardware communication tool

- **Depends**: Runtime dependencies
  - `systemd`: System service management
  - `hifiberry-eeprom`: HAT EEPROM reading
  - `avahi-daemon`: mDNS/DNS-SD discovery
  - `uuid`: Unique identifier generation
  - `i2c-tools`: Hardware communication

### debian/dirs

Directories to be created during installation:

```
etc/nginx/hifiberry-api.d     # Nginx configuration directory
usr/lib/hifiberry-configurator # Virtualenv location
etc/configserver              # Configuration directory
```

### debian/source/format

Set to `3.0 (quilt)` for modern Debian packaging:
- Supports native and non-native packages
- Enables quilt patch system for modifications
- Standard format for contemporary Debian packages

## Building the Package

### Quick Build

```bash
./build-deb-trixie.sh
```

### Manual Build

```bash
# Clean previous builds
rm -rf debian/hifiberry-configurator
rm -f debian/*.debhelper.log debian/*.substvars

# Build binary package only (no GPG signing required for local builds)
dpkg-buildpackage -us -uc -b

# Find the generated .deb file (will be in parent directory)
ls ../*.deb
```

### Full Build with Signing

```bash
# Build with GPG signing (requires configured GPG key)
dpkg-buildpackage -k<YOUR_KEY_ID>
```

### Build Source Package

```bash
# Create source package (.dsc, .tar.xz, .changes)
dpkg-buildpackage -S
```

## Build Process Details

1. **Preparation Phase**
   - Extracts source code
   - Applies any patches (if using quilt)
   - Verifies build dependencies

2. **Build Phase** (`dh_auto_build`)
   - Skipped (using pybuild)
   - dh_virtualenv handles Python build

3. **Virtualenv Creation** (`dh_virtualenv`)
   - Creates `/usr/lib/hifiberry-configurator` virtualenv
   - Installs Python 3 base environment
   - Installs requirements from `requirements.txt`
   - Compiles bytecode for faster startup
   - Optimizes package size (no pip cache)

4. **Installation Phase**
   - Installs virtualenv to debian/hifiberry-configurator/
   - Creates symlinks for entry points in `/usr/bin/`
   - Installs configuration files
   - Installs systemd services
   - Installs nginx configuration

5. **Post-Installation** (postinst)
   - Creates configuration directories
   - Sets proper file permissions
   - Enables and starts systemd services (handled by DEBHELPER#)

6. **Package Creation**
   - Creates .deb package with all contents
   - Sets proper permissions and ownership
   - Calculates package checksums

## Output Structure

After installation, the package creates:

```
/usr/lib/hifiberry-configurator/      # Virtualenv root
├── bin/                               # Executable scripts and Python
│   ├── python                         # Python interpreter
│   ├── python3                        # Python 3 interpreter
│   ├── config-*                       # CLI entry points
│   └── ...
├── lib/                               # Python packages
├── include/                           # Development headers
└── pyvenv.cfg                         # Virtualenv configuration

/usr/bin/                              # Symlinks to entry points
├── config-asoundconf
├── config-avahi
├── config-cmdline
├── ...

/etc/configserver/                     # Configuration directory
└── configserver.json

/etc/nginx/hifiberry-api.d/            # Nginx configuration
└── hifiberry-config.nginx

/etc/systemd/system/                   # Systemd services
├── volume-store.service
├── volume-store.timer
├── volume-restore.service
├── config-server.service
└── ...
```

## Verification

### Check Package Contents

```bash
# List all files in package
dpkg -c ../hifiberry-configurator_*.deb

# Check package metadata
dpkg -I ../hifiberry-configurator_*.deb

# Search for specific files
dpkg -c ../hifiberry-configurator_*.deb | grep -E "(bin/config|lib/python)"
```

### After Installation

```bash
# Check installation
dpkg -l | grep hifiberry-configurator

# Verify virtualenv works
/usr/lib/hifiberry-configurator/bin/python -V
/usr/lib/hifiberry-configurator/bin/python -m pip list

# Check entry points are available
which config-asoundconf
config-soundcard --name
```

### Verify Dependencies

```bash
# Show package dependencies
dpkg -s hifiberry-configurator | grep Depends

# Check if system dependencies are installed
dpkg -s systemd hifiberry-eeprom avahi-daemon
```

## Troubleshooting

### Build Failures

**Problem**: `dh_virtualenv: command not found`
- **Solution**: Install dh-virtualenv: `sudo apt install dh-virtualenv`

**Problem**: Build fails with "python3-dev not found"
- **Solution**: Install build dependencies: `sudo apt install python3-dev libffi-dev libssl-dev`

**Problem**: Permission denied on `/usr/lib`
- **Solution**: Build environment issue. Ensure `fakeroot` is available or run with proper permissions

### Package Installation Issues

**Problem**: "Conflicts with package X"
- **Solution**: Resolve package conflicts or use `--force-all` (not recommended)

**Problem**: Entry points not working after install
- **Solution**: Verify symlinks in `/usr/bin/`: `ls -la /usr/bin/config-*`
- Check virtualenv: `/usr/lib/hifiberry-configurator/bin/python -c "import sys; print(sys.path)"`

## Advanced Configuration

### Custom PyPI Index

To use a custom PyPI index, modify debian/rules:

```makefile
override_dh_virtualenv:
    dh_virtualenv \
        --builtin-venv \
        --install-suffix hifiberry-configurator \
        --python /usr/bin/python3 \
        --requirements requirements.txt \
        --extra-pip-arg='--index-url https://your-pypi.example.com/simple' \
        --extra-pip-arg='--no-cache-dir' \
        --extra-pip-arg='--compile'
```

### Build on Older Debian Versions

To build for Bullseye or Bookworm:

1. Update `debian/control` Build-Depends if needed
2. Ensure dh-virtualenv is available for your version
3. Run build in appropriate environment or use sbuild

### Cross-Architecture Building

For building ARM packages on x86_64:

```bash
# Install cross-compilation tools
sudo apt install crossbuild-essential-armhf

# Build for armhf architecture
dpkg-buildpackage -aarml -us -uc -b
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Debian Package
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: debian:trixie
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: |
          apt-get update
          apt-get install -y build-essential debhelper dh-virtualenv \
            python3-dev python3-pip python3-setuptools python3-wheel \
            pkg-config libffi-dev libssl-dev i2c-tools
      - name: Build package
        run: ./build-deb-trixie.sh
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: debian-packages
          path: ../*.deb
```

## References

- [dh-virtualenv Documentation](https://dh-virtualenv.readthedocs.io/)
- [Debian Maintainers Guide](https://www.debian.org/doc/manuals/maint-guide/)
- [Debian Policy Manual](https://www.debian.org/doc/debian-policy/)
- [Debhelper Reference](https://man.debian.org/debhelper)
- [pybuild Documentation](https://man.debian.org/pybuild)
