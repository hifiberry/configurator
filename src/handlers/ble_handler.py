#!/usr/bin/env python3

import logging
import subprocess
from flask import jsonify, Response

logger = logging.getLogger(__name__)

SERVICE_NAME = "ble-provisioning"


class BLEProvisioningHandler:
    """Handler for BLE provisioning API endpoints"""

    def handle_get_status(self) -> Response:
        """GET /api/v1/ble/provisioning/status"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=5,
            )
            active = result.returncode == 0
            state = result.stdout.strip() if result.stdout else "unknown"
            return jsonify(
                {
                    "status": "success",
                    "data": {"active": active, "state": state},
                }
            )
        except Exception as e:
            logger.error(f"Error checking BLE provisioning status: {e}")
            return jsonify({
                "status": "error",
                "message": str(e),
            }), 500

    def handle_start(self):
        """POST /api/v1/ble/provisioning/start

        Manual start skips the network check (ExecStartPre) by creating
        a runtime override that clears ExecStartPre.
        """
        try:
            # Create runtime override to skip ExecStartPre (network check)
            override_dir = f"/run/systemd/system/{SERVICE_NAME}.service.d"
            subprocess.run(
                ["mkdir", "-p", override_dir],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["bash", "-c",
                 f'echo -e "[Service]\\nExecStartPre=" > {override_dir}/manual.conf'],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["systemctl", "daemon-reload"],
                capture_output=True, timeout=10,
            )
            result = subprocess.run(
                ["systemctl", "start", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return jsonify({
                    "status": "success",
                    "message": "BLE provisioning started",
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to start: {result.stderr.strip()}",
                }), 500
        except Exception as e:
            logger.error(f"Error starting BLE provisioning: {e}")
            return jsonify({
                "status": "error",
                "message": str(e),
            }), 500

    def handle_stop(self):
        """POST /api/v1/ble/provisioning/stop"""
        try:
            result = subprocess.run(
                ["systemctl", "stop", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Remove runtime override so auto-start uses network check again
            override_dir = f"/run/systemd/system/{SERVICE_NAME}.service.d"
            subprocess.run(["rm", "-rf", override_dir], capture_output=True, timeout=5)
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=10)
            if result.returncode == 0:
                return jsonify({
                    "status": "success",
                    "message": "BLE provisioning stopped",
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to stop: {result.stderr.strip()}",
                }), 500
        except Exception as e:
            logger.error(f"Error stopping BLE provisioning: {e}")
            return jsonify({
                "status": "error",
                "message": str(e),
            }), 500
