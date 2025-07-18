#!/bin/bash

# Debug script for SMB mount troubleshooting
# This script provides comprehensive debugging information for SMB mount issues

echo "=== SMB Mount Debug Information ==="
echo "Timestamp: $(date)"
echo "User: $(whoami) (UID: $(id -u), GID: $(id -g))"
echo

echo "=== System Information ==="
echo "Kernel: $(uname -r)"
echo "Distribution: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')"
echo

echo "=== Network Connectivity ==="
echo "Network interfaces:"
ip addr show | grep -E '^[0-9]+:|inet '
echo

echo "=== CIFS/SMB Support ==="
echo "CIFS kernel module:"
lsmod | grep cifs || echo "CIFS module not loaded"
echo
echo "SMB utilities:"
which mount.cifs && echo "mount.cifs: $(mount.cifs --version 2>&1 | head -1)" || echo "mount.cifs not found"
which smbclient && echo "smbclient: $(smbclient --version 2>&1)" || echo "smbclient not found"
echo

echo "=== Mount Configuration Database ==="
echo "Config-sambamount binary:"
ls -la /usr/bin/config-sambamount 2>/dev/null || echo "config-sambamount not found"
echo
echo "Mount configurations in database:"
/usr/bin/config-sambamount --list-mounts --verbose 2>&1 || echo "Failed to list mount configurations"
echo

echo "=== Current Mounts ==="
echo "All current mounts:"
mount | grep -E 'cifs|smb' || echo "No CIFS/SMB mounts found"
echo
echo "Mounted directories from config:"
/usr/bin/config-sambamount --list-mounted-dirs 2>&1 || echo "Failed to list mounted directories"
echo

echo "=== Mount Points ==="
echo "Mount point directories:"
for mp in /mnt/music /mnt/data /data; do
    if [ -d "$mp" ]; then
        echo "$mp: exists ($(ls -ld "$mp"))"
        echo "  Contents: $(ls -la "$mp" 2>/dev/null | wc -l) items"
        mountpoint "$mp" >/dev/null 2>&1 && echo "  Status: MOUNTED" || echo "  Status: NOT MOUNTED"
    else
        echo "$mp: does not exist"
    fi
done
echo

echo "=== Systemd Service Status ==="
systemctl status sambamount.service --no-pager -l 2>/dev/null || echo "sambamount.service status unavailable"
echo

echo "=== Recent Service Logs ==="
journalctl -u sambamount.service --no-pager -l --since="1 hour ago" 2>/dev/null || echo "Service logs unavailable"
echo

echo "=== Manual Mount Test ==="
echo "Testing manual mount-all command:"
/usr/bin/config-sambamount --mount-all --verbose 2>&1 || echo "Manual mount-all failed"
echo

echo "=== Debug Complete ==="
