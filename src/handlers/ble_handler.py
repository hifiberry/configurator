#!/usr/bin/env python3
"""
BLE Provisioning Handler

Handles HTTP API endpoints for managing Bluetooth Low Energy (BLE) provisioning
service. Provides start/stop control and status monitoring for the ble-provisioning
systemd service.
"""

import logging
import subprocess
from typing import Union, Tuple, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Response
else:
    Response = Any

try:
    from flask import jsonify
except ImportError:
    # Flask is optional - only needed when running with Flask
    def jsonify(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        """Stub jsonify when Flask is not installed"""
        raise RuntimeError("Flask is not installed")

logger = logging.getLogger(__name__)

SERVICE_NAME = "ble-provisioning"


class BLEProvisioningHandler:
    """Handler for BLE provisioning API endpoints"""

    def handle_get_status(self) -> "Response":
        """Get BLE provisioning service status.

        Returns:
            Flask JSON response with status and service state information
        """
        try:
            result = subprocess.run(
                ["systemctl", "is-active", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
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
            logger.error("Error checking BLE provisioning status: %s", e)
            response = jsonify({
                "status": "error",
                "message": str(e),
            })
            response.status_code = 500
            return response

    def handle_start(self) -> Union["Response", Tuple["Response", int]]:
        """Start BLE provisioning service.

        Manual start skips the network check (ExecStartPre) by creating
        a runtime override that clears ExecStartPre.

        Returns:
            Flask JSON response with status message, or tuple with response and status code on error
        """
        try:
            # Create runtime override to skip ExecStartPre (network check)
            override_dir = f"/run/systemd/system/{SERVICE_NAME}.service.d"
            subprocess.run(
                ["mkdir", "-p", override_dir],
                capture_output=True, timeout=5,
                check=False,
            )
            subprocess.run(
                ["bash", "-c",
                 f'echo -e "[Service]\\nExecStartPre=" > {override_dir}/manual.conf'],
                capture_output=True, timeout=5,
                check=False,
            )
            subprocess.run(
                ["systemctl", "daemon-reload"],
                capture_output=True, timeout=10,
                check=False,
            )
            result = subprocess.run(
                ["systemctl", "start", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return jsonify({
                    "status": "success",
                    "message": "BLE provisioning started",
                })
            return jsonify({
                "status": "error",
                "message": f"Failed to start: {result.stderr.strip()}",
            }), 500
        except Exception as e:
            logger.error("Error starting BLE provisioning: %s", e)
            return jsonify({
                "status": "error",
                "message": str(e),
            }), 500

    def handle_stop(self) -> Union["Response", Tuple["Response", int]]:
        """Stop BLE provisioning service.

        Removes runtime override so auto-start uses network check again.

        Returns:
            Flask JSON response with status message, or tuple with response and status code on error
        """
        try:
            result = subprocess.run(
                ["systemctl", "stop", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            # Remove runtime override so auto-start uses network check again
            override_dir = f"/run/systemd/system/{SERVICE_NAME}.service.d"
            subprocess.run(
                ["rm", "-rf", override_dir],
                capture_output=True, timeout=5, check=False
            )
            subprocess.run(
                ["systemctl", "daemon-reload"],
                capture_output=True, timeout=10, check=False
            )
            if result.returncode == 0:
                return jsonify({
                    "status": "success",
                    "message": "BLE provisioning stopped",
                })
            return jsonify({
                "status": "error",
                "message": f"Failed to stop: {result.stderr.strip()}",
            }), 500
        except Exception as e:
            logger.error("Error stopping BLE provisioning: %s", e)
            return jsonify({
                "status": "error",
                "message": str(e),
            }), 500
