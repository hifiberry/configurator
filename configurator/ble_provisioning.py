#!/usr/bin/env python3
"""
BLE WiFi Provisioning Server for HiFiBerryOS

Exposes a BLE GATT server that allows a mobile app to:
- View device identity and network status
- Scan for WiFi networks
- Connect to a WiFi network
- Stop the BLE server after provisioning

Runs as a standalone systemd service (ble-provisioning.service),
controlled by the config-server Flask API via systemctl.
"""

import asyncio
import json
import logging
import platform
import signal
import subprocess
import sys
import argparse
from typing import Any, Dict, List, Optional

from bless import (
    BlessGATTCharacteristic,
    BlessServer,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)

from . import wifi, network

logger = logging.getLogger(__name__)

# Custom GATT service UUID
SERVICE_UUID = "d5ae7526-9739-4baa-b9c0-5e5c11be9875"

# Characteristic UUIDs (share the same prefix, differ by suffix)
_BASE = "d5ae7526-9739-4baa-b9c0-5e5c11be"
CHAR_DEVICE_IDENTITY = f"{_BASE}0001"
CHAR_NETWORK_STATUS = f"{_BASE}0002"
CHAR_WIFI_SCAN_TRIGGER = f"{_BASE}0003"
CHAR_WIFI_SCAN_RESULTS = f"{_BASE}0004"
CHAR_WIFI_CONNECT = f"{_BASE}0005"
CHAR_WIFI_CONNECT_STATUS = f"{_BASE}0006"
CHAR_BLE_CONTROL = f"{_BASE}0007"

MAX_SCAN_RESULTS = 20


class BLEProvisioningServer:
    """BLE GATT server for WiFi provisioning."""

    def __init__(self):
        self.server: Optional[BlessServer] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Cached state
        self._scan_results: List[Dict[str, Any]] = []
        self._connect_status: Dict[str, str] = {
            "state": "idle",
            "ssid": "",
            "error": "",
        }
        self._shutdown_requested = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_hostname(self) -> str:
        return platform.node()

    def _get_device_identity(self) -> bytes:
        hostname = self._get_hostname()
        model = ""
        version = ""
        try:
            from ._version import __version__
            version = __version__
        except Exception:
            pass
        try:
            from .pimodel import PiModel
            pi = PiModel()
            model = pi.model or ""
        except Exception:
            pass
        data = {"hostname": hostname, "model": model, "version": version}
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def _get_network_status(self) -> bytes:
        try:
            cfg = network.get_network_config()
        except Exception as e:
            logger.error(f"Error getting network config: {e}")
            cfg = {"hostname": self._get_hostname(), "interfaces": []}

        wifi_connected = False
        wifi_ssid = ""
        wifi_ip = ""
        eth_connected = False
        eth_ip = ""

        for iface in cfg.get("interfaces", []):
            ip = iface.get("ipv4") or ""
            if iface.get("type") == "wireless":
                if ip:
                    wifi_connected = True
                    wifi_ip = ip
            else:
                if ip:
                    eth_connected = True
                    eth_ip = ip

        if wifi_connected:
            try:
                conn = wifi.get_current_connection()
                if conn:
                    wifi_ssid = conn.get("ssid", "")
            except Exception:
                pass

        data = {
            "wifi_connected": wifi_connected,
            "wifi_ssid": wifi_ssid,
            "wifi_ip": wifi_ip,
            "eth_connected": eth_connected,
            "eth_ip": eth_ip,
            "hostname": cfg.get("hostname", self._get_hostname()),
        }
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def _get_scan_results_bytes(self) -> bytes:
        return json.dumps(self._scan_results, separators=(",", ":")).encode("utf-8")

    def _get_connect_status_bytes(self) -> bytes:
        return json.dumps(self._connect_status, separators=(",", ":")).encode("utf-8")

    # ------------------------------------------------------------------
    # GATT callbacks
    # ------------------------------------------------------------------

    def _on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        uuid = characteristic.uuid.lower()
        logger.debug(f"Read request for {uuid}")

        if uuid == CHAR_DEVICE_IDENTITY:
            return bytearray(self._get_device_identity())
        elif uuid == CHAR_NETWORK_STATUS:
            return bytearray(self._get_network_status())
        elif uuid == CHAR_WIFI_SCAN_RESULTS:
            return bytearray(self._get_scan_results_bytes())
        elif uuid == CHAR_WIFI_CONNECT_STATUS:
            return bytearray(self._get_connect_status_bytes())

        return bytearray(b"")

    def _on_write(self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs):
        uuid = characteristic.uuid.lower()
        logger.debug(f"Write request for {uuid}, value={value!r}")

        if uuid == CHAR_WIFI_SCAN_TRIGGER:
            self._handle_scan_trigger(value)
        elif uuid == CHAR_WIFI_CONNECT:
            self._handle_wifi_connect(value)
        elif uuid == CHAR_BLE_CONTROL:
            self._handle_ble_control(value)

    # ------------------------------------------------------------------
    # Write handlers
    # ------------------------------------------------------------------

    def _handle_scan_trigger(self, value: Any):
        """Handle WiFi scan trigger write."""
        raw = bytes(value) if not isinstance(value, bytes) else value
        if raw and raw[0] == 0xFF:
            logger.info("WiFi scan triggered via BLE")
            asyncio.ensure_future(self._do_wifi_scan())

    async def _do_wifi_scan(self):
        """Run WiFi scan in a thread to avoid blocking the event loop."""
        try:
            results = await asyncio.to_thread(wifi.scan_wifi_networks, 10)
            self._scan_results = [
                {
                    "ssid": n.get("ssid", ""),
                    "signal": n.get("signal", 0),
                    "security": n.get("security", ""),
                }
                for n in results[:MAX_SCAN_RESULTS]
            ]
            logger.info(f"WiFi scan complete: {len(self._scan_results)} networks")
        except Exception as e:
            logger.error(f"WiFi scan failed: {e}")
            self._scan_results = []

        # Update the characteristic value and notify
        if self.server:
            self.server.get_characteristic(CHAR_WIFI_SCAN_RESULTS).value = (
                bytearray(self._get_scan_results_bytes())
            )
            self.server.update_value(SERVICE_UUID, CHAR_WIFI_SCAN_RESULTS)

    def _handle_wifi_connect(self, value: Any):
        """Handle WiFi connect write."""
        try:
            raw = bytes(value) if not isinstance(value, bytes) else value
            payload = json.loads(raw.decode("utf-8"))
            ssid = payload.get("ssid", "")
            passphrase = payload.get("passphrase")
            if not ssid:
                logger.warning("WiFi connect: empty SSID")
                return
            logger.info(f"WiFi connect requested for SSID: {ssid}")
            self._connect_status = {"state": "connecting", "ssid": ssid, "error": ""}
            self._notify_connect_status()
            asyncio.ensure_future(self._do_wifi_connect(ssid, passphrase))
        except Exception as e:
            logger.error(f"Error parsing WiFi connect payload: {e}")
            self._connect_status = {
                "state": "failed",
                "ssid": "",
                "error": str(e),
            }
            self._notify_connect_status()

    async def _do_wifi_connect(self, ssid: str, passphrase: Optional[str]):
        """Run WiFi connect in a thread."""
        try:
            success = await asyncio.to_thread(
                wifi.connect_to_wifi, ssid, passphrase, False
            )
            if success:
                self._connect_status = {
                    "state": "connected",
                    "ssid": ssid,
                    "error": "",
                }
                logger.info(f"WiFi connected to {ssid}")
            else:
                self._connect_status = {
                    "state": "failed",
                    "ssid": ssid,
                    "error": "Connection failed",
                }
                logger.warning(f"WiFi connection to {ssid} failed")
        except Exception as e:
            self._connect_status = {
                "state": "failed",
                "ssid": ssid,
                "error": str(e),
            }
            logger.error(f"WiFi connection error: {e}")

        self._notify_connect_status()
        # Also update network status characteristic
        if self.server:
            self.server.get_characteristic(CHAR_NETWORK_STATUS).value = (
                bytearray(self._get_network_status())
            )
            self.server.update_value(SERVICE_UUID, CHAR_NETWORK_STATUS)

    def _handle_ble_control(self, value: Any):
        """Handle BLE control write."""
        try:
            raw = bytes(value) if not isinstance(value, bytes) else value
            payload = json.loads(raw.decode("utf-8"))
            action = payload.get("action", "")
            if action == "stop_ble":
                logger.info("BLE stop requested via GATT control")
                self._shutdown_requested = True
                if self.loop:
                    self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception as e:
            logger.error(f"Error parsing BLE control payload: {e}")

    def _notify_connect_status(self):
        """Push connect status notification."""
        if self.server:
            self.server.get_characteristic(CHAR_WIFI_CONNECT_STATUS).value = (
                bytearray(self._get_connect_status_bytes())
            )
            self.server.update_value(SERVICE_UUID, CHAR_WIFI_CONNECT_STATUS)

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the BLE GATT server."""
        hostname = self._get_hostname()
        # Truncate to fit BLE advertising name limit (~29 bytes)
        adv_name = f"HiFiBerry-{hostname}"[:29]
        logger.info(f"Starting BLE provisioning server as '{adv_name}'")

        self.server = BlessServer(name=adv_name, loop=asyncio.get_event_loop())
        self.server.read_request_func = self._on_read
        self.server.write_request_func = self._on_write

        await self.server.add_new_service(SERVICE_UUID)

        # Device Identity — Read
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_DEVICE_IDENTITY,
            GATTCharacteristicProperties.read,
            bytearray(self._get_device_identity()),
            GATTAttributePermissions.readable,
        )

        # Network Status — Read + Notify
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_NETWORK_STATUS,
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.notify,
            bytearray(self._get_network_status()),
            GATTAttributePermissions.readable,
        )

        # WiFi Scan Trigger — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_WIFI_SCAN_TRIGGER,
            GATTCharacteristicProperties.write,
            bytearray(b"\x00"),
            GATTAttributePermissions.writeable,
        )

        # WiFi Scan Results — Read + Notify
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_WIFI_SCAN_RESULTS,
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.notify,
            bytearray(b"[]"),
            GATTAttributePermissions.readable,
        )

        # WiFi Connect — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_WIFI_CONNECT,
            GATTCharacteristicProperties.write,
            bytearray(b""),
            GATTAttributePermissions.writeable,
        )

        # WiFi Connect Status — Read + Notify
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_WIFI_CONNECT_STATUS,
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.notify,
            bytearray(self._get_connect_status_bytes()),
            GATTAttributePermissions.readable,
        )

        # BLE Control — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_BLE_CONTROL,
            GATTCharacteristicProperties.write,
            bytearray(b""),
            GATTAttributePermissions.writeable,
        )

        await self.server.start()
        logger.info("BLE GATT server started and advertising")

    async def stop(self):
        """Stop the BLE server."""
        if self.server:
            logger.info("Stopping BLE GATT server")
            await self.server.stop()
            self.server = None


# ------------------------------------------------------------------
# Network connectivity check
# ------------------------------------------------------------------


def has_network_connectivity() -> bool:
    """Check if any network interface has an IP address."""
    try:
        interfaces = network.list_physical_interfaces()
        for iface in interfaces:
            if iface.get("ipv4"):
                return True
    except Exception as e:
        logger.error(f"Error checking network connectivity: {e}")
    return False


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def setup_logging(verbose: bool = False):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    root.addHandler(handler)


def main():
    parser = argparse.ArgumentParser(
        description="HiFiBerry BLE WiFi Provisioning"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check-network",
        action="store_true",
        help="Exit 0 if no network (BLE should start), exit 1 if network exists",
    )
    group.add_argument(
        "--serve", action="store_true", help="Start the BLE GATT server"
    )
    group.add_argument(
        "--stop",
        action="store_true",
        help="Stop the BLE provisioning service via systemctl",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.check_network:
        if has_network_connectivity():
            logger.info("Network connectivity detected — skipping BLE provisioning")
            sys.exit(1)  # non-zero → systemd skips ExecStart
        else:
            logger.info("No network connectivity — BLE provisioning should start")
            sys.exit(0)

    if args.stop:
        subprocess.run(
            ["systemctl", "stop", "ble-provisioning"],
            capture_output=True,
            timeout=10,
        )
        sys.exit(0)

    if args.serve:
        provisioner = BLEProvisioningServer()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        provisioner.loop = loop

        # Handle SIGTERM/SIGINT for clean shutdown
        def _signal_handler():
            logger.info("Signal received, shutting down")
            loop.stop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _signal_handler)

        try:
            loop.run_until_complete(provisioner.start())
            loop.run_forever()
        except Exception as e:
            logger.error(f"BLE server error: {e}")
        finally:
            loop.run_until_complete(provisioner.stop())
            loop.close()
            logger.info("BLE provisioning server stopped")


if __name__ == "__main__":
    main()
