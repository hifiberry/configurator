# Debian Trixie Build System with dh_virtualenv

## Quick Start

### 1. Setup Build Environment (First Time Only)

```bash
./setup-build-env.sh
```

This script installs all required build tools:
- Build essentials (gcc, make, debhelper)
- dh-virtualenv package builder
- Python 3 development headers
- System libraries (libffi-dev, libssl-dev, i2c-tools)

### 2. Build the Package

```bash
DIST=trixie ./build-deb.sh
```

The script will:
1. Create an sbuild chroot for Trixie
2. Install build dependencies
3. Create a virtualenv with all Python dependencies via dh_virtualenv
4. Package everything into a .deb file
5. Display the generated package(s)

### 3. Install the Package

```bash
sudo dpkg -i ../hifiberry-configurator_*.deb
```

## What is dh_virtualenv?

dh_virtualenv is a tool that packages a Python application with all its dependencies into a self-contained virtualenv inside a Debian package.

**Benefits:**
- ✅ **Isolation**: All Python packages in one virtualenv
- ✅ **Reproducibility**: Consistent versions everywhere
- ✅ **Simplicity**: No system Python dependency management
- ✅ **Flexibility**: Works on minimal systems

**Drawback:**
- ❌ Larger package size (includes entire Python environment)

## Build System Overview

### File Structure

```
hifiberry-configurator/
├── setup.py                           # Python package metadata
├── requirements.txt                   # Python dependencies
├── build-deb.sh                      # Build script (uses sbuild)
├── setup-build-env.sh                # Environment setup (executable)
├── DEBIAN_BUILD.md                   # Detailed build documentation
├── DEBIAN_TRIXIE_CONFIG.md          # Configuration reference
│
└── debian/                           # Debian packaging
    ├── rules                         # Build rules (dh_virtualenv config)
    ├── control                       # Package metadata & dependencies
    ├── source/
    │   └── format (3.0 quilt)       # Modern Debian source format
    ├── dirs                          # Directories to create
    ├── .gitignore                    # Build artifacts to ignore
    ├── hifiberry-configurator.install # Files to install
    ├── hifiberry-configurator.postinst # Post-install hook
    ├── hifiberry-configurator.prerm   # Pre-remove hook
    ├── changelog                     # Version history
    └── copyright                     # License information
```

### Build Process

```
┌──────────────────────────────────────┐
│ DIST=trixie ./build-deb.sh           │
└──────────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ sbuild (chroot mode)     │
    │ Target: Trixie           │
    └──────────────┬───────────┘
                   │
                   ▼
    ┌──────────────────────────┐
    │ dpkg-buildpackage        │
    └──────────────┬───────────┘
                   │
                   ▼
    ┌──────────────────────────┐
    │ debian/rules             │
    │ (with virtualenv handler)│
    └──────────────┬───────────┘
                   │
                   ▼
    ┌──────────────────────────┐
    │ dh_virtualenv            │
    │ ├─ Create virtualenv     │
    │ ├─ Install requirements  │
    │ ├─ Compile bytecode      │
    │ └─ Create entry points   │
    └──────────────┬───────────┘
                   ▼
    ┌──────────────────────────┐
    │ Install system files     │
    │ ├─ Config files          │
    │ ├─ Systemd services      │
    │ ├─ Nginx config          │
    │ └─ Man pages             │
    └──────────────┬───────────┘
                   ▼
    ┌──────────────────────────┐
    │ Create .deb package      │
    └──────────────┬───────────┘
                   ▼
    ../hifiberry-configurator_*.deb
```

## Debian Configuration

### debian/rules

The rules file controls the build process:

```makefile
# Use dh_virtualenv sequencer
%:
    dh $@ --with virtualenv --buildsystem=pybuild

# Configure virtualenv creation
override_dh_virtualenv:
    dh_virtualenv \
        --builtin-venv                    # Use Python's built-in venv
        --install-suffix hifiberry-configurator  # Virtualenv path
        --python /usr/bin/python3         # Python interpreter
        --requirements requirements.txt    # Dependencies file
        --extra-pip-arg='--no-cache-dir' # Optimize size
        --extra-pip-arg='--compile'       # Pre-compile Python
```

### debian/control

Specifies package metadata:

```
Source: hifiberry-configurator

Build-Depends:
  - debhelper-compat (= 13) - Modern debhelper version
  - dh-virtualenv - Python virtualenv packager
  - python3-dev - Development headers
  - libffi-dev, libssl-dev - Build dependencies for packages like cryptography

Depends:
  - systemd - System service management
  - hifiberry-eeprom - HAT EEPROM reading
  - avahi-daemon - mDNS/DNS-SD discovery
  - uuid - Unique ID generation
  - i2c-tools - I2C hardware communication
```

Note: Dependencies like `python3-netifaces`, `python3-dbus`, etc. are NOT required
because they're vendored in the virtualenv.

### debian/source/format

```
3.0 (quilt)
```

Modern Debian source format with support for quilt patches. Supports proper
source code organization and patch management.

## Installation Structure

After installation, the package creates:

```
/usr/lib/hifiberry-configurator/
├── bin/
│   ├── python, python3           # Python interpreter
│   ├── config-soundcard          # CLI entry points
│   ├── config-volume
│   ├── config-server
│   └── ... (15+ scripts total)
├── lib/
│   └── python3.x/site-packages/  # All Python packages
│       ├── cryptography
│       ├── flask
│       ├── netifaces
│       ├── configurator          # The app itself
│       └── ... (all dependencies)
├── include/
│   └── (Development headers)
└── pyvenv.cfg

/usr/bin/                          # Symlinks to scripts
├── config-soundcard -> ../lib/hifiberry-configurator/bin/config-soundcard
├── config-volume -> ...
└── ... (all entry points symlinked)

/etc/systemd/system/              # System services
├── volume-restore.service
├── config-server.service
└── ... (7 services total)

/etc/configserver/                # Configuration
└── configserver.json

/etc/nginx/hifiberry-api.d/       # Web server config
└── hifiberry-config.nginx
```

## Verification

### After Setup

```bash
# Check tools are available
dpkg --version          # Should show debhelper
dh_virtualenv --version # Should show dh-virtualenv
python3 --version       # Should show Python 3.x

# Check build dependencies
dpkg-checkbuilddeps     # Should show "Build dependencies satisfied"
```

### After Build

```bash
# List package contents
dpkg -c ../hifiberry-configurator_*.deb | head -20

# Check package metadata
dpkg -I ../hifiberry-configurator_*.deb

# Check package size
ls -lh ../hifiberry-configurator_*.deb
```

### After Installation

```bash
# Verify installation
dpkg -l | grep hifiberry-configurator

# Test virtualenv
/usr/lib/hifiberry-configurator/bin/python -c "import sys; print(sys.path)"

# List installed modules
/usr/lib/hifiberry-configurator/bin/pip list

# Test entry point
config-soundcard --help

# Check services
systemctl list-units --type service | grep hifiberry
```

## Common Tasks

### View Build Output

```bash
# Verbose build output
DH_VERBOSE=1 dpkg-buildpackage -us -uc -b

# Show build commands
dpkg-buildpackage -us -uc -b --verbose
```

### Clean Build Artifacts

```bash
# Quick clean
rm -rf debian/hifiberry-configurator
rm -f debian/*.debhelper.log debian/*.substvars

# Complete clean
rm -rf debian/hifiberry-configurator build dist *.egg-info
rm -f debian/*.debhelper.log debian/*.substvars
```

### Rebuild from Scratch

```bash
DIST=trixie ./build-deb.sh
```

### Check What's in the Package

```bash
# List all files
dpkg -c ../hifiberry-configurator_*.deb

# Count files
dpkg -c ../hifiberry-configurator_*.deb | wc -l

# Check for specific file
dpkg -c ../hifiberry-configurator_*.deb | grep config-soundcard
```

### Extract Package Contents

```bash
# Extract to directory
dpkg-deb -x ../hifiberry-configurator_*.deb extracted/

# Inspect control files
dpkg-deb -e ../hifiberry-configurator_*.deb extracted/DEBIAN/
```

## Troubleshooting

### Build Fails with "dh_virtualenv: command not found"

**Solution**: Install dh-virtualenv
```bash
sudo apt install dh-virtualenv
```

### Build Fails with "python3-dev not found"

**Solution**: Run setup script
```bash
./setup-build-env.sh
```

### Build Fails with "i2c-tools not installed"

**Solution**: Install missing package
```bash
sudo apt install i2c-tools
```

### Build Fails with "No space left on device"

**Solution**: Clear build cache
```bash
rm -rf ~/.cache/pip
./build-deb-trixie.sh
```

### Package Too Large

**Issue**: The virtualenv includes everything, making the package large
**Solution**: This is expected. The size includes:
  - Complete Python 3 interpreter
  - All dependencies
  - Pre-compiled bytecode

**To reduce size** (not recommended):
- Remove bytecode: `--extra-pip-arg='--no-compile'`
- Use pypy3: Change `--python /usr/bin/pypy3`
- Remove optional dependencies from requirements.txt

### Systemd Services Not Starting

**Check**: 
```bash
systemctl status config-server.service
journalctl -u config-server.service -n 20

# Verify virtualenv works
/usr/lib/hifiberry-configurator/bin/python -c "import configurator"
```

**Common causes**:
- Missing runtime dependencies (systemd, i2c-tools)
- Insufficient permissions for I2C access
- Configuration directory not writable

## Advanced Usage

### Build for Different Python Version

Edit debian/rules:
```makefile
--python /usr/bin/python3.11
```

### Use Different PyPI Index

Edit debian/rules:
```makefile
--extra-pip-arg='--index-url https://your-pypi.example.com/simple'
```

### Build Faster with Cache

```bash
# Keep pip cache
# (by default --no-cache-dir is used for smaller package)
```

### Build Source Package

```bash
# Create .dsc and .tar.xz
dpkg-buildpackage -S

# Sign with GPG
dpkg-buildpackage -k<keyid> -S
```

### Build in Docker

```dockerfile
FROM debian:trixie
RUN apt-get update && apt-get install -y \
    build-essential debhelper dh-virtualenv \
    python3-dev python3-pip python3-setuptools python3-wheel \
    pkg-config libffi-dev libssl-dev i2c-tools
WORKDIR /src
COPY . .
RUN ./build-deb-trixie.sh
```

## Documentation

- **DEBIAN_BUILD.md** - Comprehensive build guide with all details
- **DEBIAN_TRIXIE_CONFIG.md** - Configuration quick reference
- **debian/rules** - Build rule implementation
- **debian/control** - Package metadata

## Support

For issues or questions:
1. Check DEBIAN_BUILD.md for detailed information
2. Review debian/rules for build configuration
3. Check dh_virtualenv documentation: https://dh-virtualenv.readthedocs.io/
4. Review Debian packaging guide: https://www.debian.org/doc/manuals/maint-guide/

## See Also

- `setup-build-env.sh` - Install build environment
- `build-deb-trixie.sh` - Build the package
- `debian/rules` - Build rules
- `debian/control` - Package metadata
