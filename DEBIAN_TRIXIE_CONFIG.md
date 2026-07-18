# Debian Trixie Build Configuration Summary

## Current Configuration

### Build Tool: dh_virtualenv
- **Location**: Virtualenv installed to `/usr/lib/hifiberry-configurator`
- **Python**: System Python 3 (`/usr/bin/python3`)
- **Dependencies**: Vendored in virtualenv (from requirements.txt)

### Debian Parameters
- **Format**: 3.0 (quilt) - Modern Debian source format
- **Debhelper Compat**: 13 (Trixie compatible)
- **Architecture**: any (architecture-independent)
- **Maintainer**: HiFiBerry <support@hifiberry.com>

### Key Files

#### debian/rules
- Sequencer: `dh --with virtualenv --buildsystem=pybuild`
- Overrides: 
  - `dh_virtualenv`: Configures virtualenv creation
  - `dh_auto_build`: Skipped (pybuild handled)
  - `dh_auto_install`: Skipped (dh_virtualenv handled)
  - `dh_installsystemd`: Configures services
  - `dh_fixperms`: Ensures proper permissions

#### debian/control
- **Build-Depends**:
  - debhelper-compat (= 13)
  - dh-virtualenv
  - python3-dev, python3-pip, python3-setuptools, python3-wheel
  - libffi-dev, libssl-dev (for cryptography)
  - pkg-config, i2c-tools

- **Depends**:
  - systemd (service management)
  - hifiberry-eeprom (HAT detection)
  - avahi-daemon (mDNS discovery)
  - uuid (UUID generation)
  - i2c-tools (hardware access)

#### debian/source/format
- `3.0 (quilt)` - Modern format with patch support

#### debian/dirs
- `etc/nginx/hifiberry-api.d` - Web API config
- `usr/lib/hifiberry-configurator` - Virtualenv
- `etc/configserver` - Config directory

### Build Process Flow

```
1. Prepare (extract, patch)
2. Configure (dh_auto_configure - skipped)
3. Build (dh_auto_build - skipped)
4. Install (dh_virtualenv)
   ├─ Create virtualenv at /usr/lib/hifiberry-configurator
   ├─ Install requirements.txt packages
   ├─ Compile bytecode
   ├─ Create entry points in /usr/bin/
   └─ Optimize for size (no cache, compiled)
5. Install system files
   ├─ Configuration files
   ├─ Systemd services  
   ├─ Nginx configuration
   └─ Man pages
6. Post-install (postinst)
   ├─ Create directories
   ├─ Set permissions
   └─ Enable services (via DEBHELPER#)
7. Create .deb package
```

### Installation Result

After `apt install hifiberry-configurator`:

```
Package Contents:
├── /usr/lib/hifiberry-configurator/    ← Complete virtualenv
├── /usr/bin/config-*                   ← Entry points/scripts
├── /etc/configserver/configserver.json
├── /etc/nginx/hifiberry-api.d/
├── /etc/systemd/system/volume-*.service
├── /usr/share/man/man1/config-*.1
└── /usr/share/doc/hifiberry-configurator/

Systemd Services:
├── volume-store.service
├── volume-store.timer
├── volume-restore.service
├── config-server.service
├── config-detect.service
└── ble-provisioning.service
```

### Entry Points

The virtualenv automatically creates executable scripts in `/usr/lib/hifiberry-configurator/bin/`:

From setup.py:
- config-asoundconf
- config-configtxt
- config-hattools
- config-detect
- config-detectpi
- config-soundcard
- config-cmdline
- config-sambaclient
- config-sambamount
- config-wifi
- config-network
- config-db
- config-volume
- config-avahi
- config-server
- config-pipewire
- config-ble-provision

dh_virtualenv creates symlinks in `/usr/bin/` for user access.

## Building

### Quick Build
```bash
./build-deb-trixie.sh
```

### Check Build
```bash
# Verify dependencies
dpkg-checkbuilddeps

# Build with verbose output
dpkg-buildpackage -us -uc -b -v
```

### Verify Package
```bash
# List contents
dpkg -c ../hifiberry-configurator_*.deb | head -20

# Check dependencies
dpkg -I ../hifiberry-configurator_*.deb | grep Depends
```

## Installation

### Install Package
```bash
sudo dpkg -i hifiberry-configurator_*.deb
```

### Verify Installation
```bash
# Check package
dpkg -l | grep hifiberry-configurator

# Test virtualenv
/usr/lib/hifiberry-configurator/bin/python -V

# Test entry point
config-soundcard --name

# Check services
systemctl status volume-restore.service
```

## Customization

### Change Virtualenv Location
Edit debian/rules override_dh_virtualenv:
```makefile
--install-suffix hifiberry-configurator-custom
```

### Add/Remove Dependencies
Edit debian/control Build-Depends or Depends sections.

### Modify Build Options
Edit debian/rules --extra-pip-arg options.

### Change Debhelper Version
Edit debian/control Build-Depends:
```
debhelper-compat (= 13)  ← Change version
```

## Troubleshooting

### Build on Trixie
```bash
# Ensure Trixie packages
apt list --upgradable

# Install latest build tools
sudo apt install --upgrade dh-virtualenv debhelper python3-dev
```

### Build in Docker/Container
```dockerfile
FROM debian:trixie
RUN apt-get update && apt-get install -y \
    build-essential debhelper dh-virtualenv \
    python3-dev python3-pip python3-setuptools python3-wheel \
    pkg-config libffi-dev libssl-dev i2c-tools
WORKDIR /build
COPY . .
RUN ./build-deb-trixie.sh
```

## Useful Commands

```bash
# Check for build issues before building
dpkg-checkbuilddeps

# Build with detailed output
DH_VERBOSE=1 dpkg-buildpackage -us -uc -b

# Check installed package
dpkg -s hifiberry-configurator

# List files in installed package
dpkg -L hifiberry-configurator

# Uninstall package
sudo apt remove hifiberry-configurator

# Clean build artifacts
rm -rf debian/hifiberry-configurator
rm -f debian/*.debhelper.log debian/*.substvars
rm -rf build dist *.egg-info
```

## More Information

- Build script: `build-deb-trixie.sh`
- Detailed guide: `DEBIAN_BUILD.md`
- Debian policy: `debian/rules`, `debian/control`, `debian/source/format`
