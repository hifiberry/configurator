# HiFiBerry Configurator

System configuration scripts for HiFiBerry audio devices and network management.

## Network Configuration

The `config-network` command provides comprehensive network interface management.

### Basic Usage

```bash
# List all physical network interfaces
config-network --list-interfaces

# List interfaces with detailed information
config-network --list-interfaces --long

# Configure interface to use DHCP
config-network --set-dhcp eth0

# Configure interface with static IP
config-network --set-fixed eth0 --ip 192.168.1.100/24 --router 192.168.1.1
```

### IPv6 Management

System-wide IPv6 can be enabled or disabled with persistent settings across reboots:

```bash
# Enable IPv6 system-wide
config-network --enable-ipv6

# Disable IPv6 system-wide
config-network --disable-ipv6
```

#### IPv6 Configuration Details

When enabling/disabling IPv6, the tool configures multiple layers for comprehensive control:

1. **Kernel Parameters**: Manages `ipv6.disable=1` in `/boot/firmware/cmdline.txt` or `/boot/cmdline.txt`
2. **Sysctl Settings**: Creates/removes configuration files in `/etc/sysctl.d/`
3. **NetworkManager**: Updates all connection profiles to enable/disable IPv6
4. **Service Management**: Restarts NetworkManager to apply changes immediately

**Note**: A reboot may be required for kernel-level IPv6 changes to take full effect.

### Verbose Output

Use `-v` or `--verbose` for detailed logging, or `-q` or `--quiet` to suppress non-error output:

```bash
config-network --enable-ipv6 --verbose
config-network --list-interfaces --quiet
```

## Other Configuration Tools

- `config-asoundconf` - ALSA sound configuration
- `config-configtxt` - Raspberry Pi config.txt management
- `config-hattools` - HAT EEPROM tools
- `config-detect` - Sound card detection
- `config-detectpi` - Raspberry Pi model detection
- `config-soundcard` - Sound card configuration
- `config-cmdline` - Kernel command line management
- `config-sambaclient` - Samba client configuration
- `config-sambamount` - Samba mount management
- `config-wifi` - WiFi configuration
- `config-db` - Configuration database
- `config-volume` - Volume control
- `config-avahi` - Avahi service configuration

## Requirements

- Python 3.6+
- NetworkManager (for network configuration)
- netifaces
- Root privileges (for system configuration changes)

## Installation

This package is typically installed as part of HiFiBerry OS. For manual installation:

```bash
pip install -r requirements.txt
python setup.py install
```
