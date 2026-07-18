"""Bluetooth Handler

Handles HTTP API endpoints for Bluetooth configuration and device management.
Provides endpoints for getting/setting Bluetooth settings, managing paired devices,
and handling passkey/modal requests for Bluetooth interactions.
"""

import logging
from typing import Any, Dict, Optional, Union, cast, TYPE_CHECKING

from ..bluetooth import (
    get_bluetooth_settings,
    set_bluetooth_settings,
    get_paired_devices,
    unpair_device,
)  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from flask import Response
else:
    Response = Any

try:
    from flask import jsonify, request
except ImportError:
    # Flask is optional - only needed when running with Flask
    def jsonify(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        """Stub jsonify when Flask is not installed"""
        raise RuntimeError("Flask is not installed")

    # Create a stub request object for type checking
    class StubArgs:  # pylint: disable=too-few-public-methods
        """Stub args object when Flask is not installed"""

        def get(self, _key: str, default: Any = None) -> Any:  # type: ignore
            """Stub get method"""
            return default

    class StubJson:  # pylint: disable=too-few-public-methods
        """Stub json object when Flask is not installed"""

        def get(self, _key: str, default: Any = None) -> Any:  # type: ignore
            """Stub get method"""
            return default

    class StubRequest:  # pylint: disable=too-few-public-methods
        """Stub request object when Flask is not installed"""
        args: StubArgs = StubArgs()
        json: Optional[Dict[str, Any]] = None
        is_json: bool = False

    request = StubRequest()  # type: ignore

logger = logging.getLogger(__name__)

class BluetoothHandler:
    """Handler for bluetooth configuration API endpoints"""
    passkey: Optional[str] = None
    show_modal: Optional[str] = None

    def __init__(self) -> None:
        """Initialize the bluetooth handler"""
        self.passkey: Optional[str] = None
        self.show_modal: Optional[str] = None

    def handle_get_bluetooth_passkey(self) -> Union["Response", tuple["Response", int]]:
        """Return the stored passkey and delete it afterwards.

        Returns:
            Flask JSON response with passkey value
        """
        value: Optional[str] = self.passkey
        self.passkey = None
        return jsonify({  # type: ignore[return-value]
            'status': 'success',
            'passkey': value
        })

    def handle_set_bluetooth_passkey(self) -> Union["Response", tuple["Response", int]]:
        """Store the provided Bluetooth passkey.

        Retrieves passkey from request args or JSON body and stores it for later retrieval.

        Returns:
            Flask JSON response indicating success or error
        """
        try:
            pk: Optional[str] = (
                request.args.get("passkey")  # type: ignore
                or (request.json.get("passkey")  # type: ignore
                    if request.is_json else None)
            )

            if not pk:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'No passkey provided'
                }), 400

            self.passkey = pk

            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'message': 'Passkey stored successfully'
            })

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error setting Bluetooth passkey: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to store passkey",
                "error": str(e),
            }), 500

    def handle_set_show_modal(self) -> Union["Response", tuple["Response", int]]:
        """Store a modal request payload or identifier.

        Retrieves modal value from request args or JSON body and stores it for later retrieval.

        Returns:
            Flask JSON response indicating success or error
        """
        try:
            modal: Optional[str] = (
                request.args.get("modal")  # type: ignore
                or (request.json.get("modal")  # type: ignore
                    if request.is_json else None)
            )

            if not modal:
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'No modal value provided'
                }), 400

            self.show_modal = modal

            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'message': 'Modal request stored successfully'
            })

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error setting modal: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to store modal request",
                "error": str(e),
            }), 500

    def handle_get_show_modal(self) -> Union["Response", tuple["Response", int]]:
        """Return the stored modal request and clear it.

        Returns:
            Flask JSON response with modal value
        """
        value: Optional[str] = self.show_modal
        self.show_modal = None
        return jsonify({  # type: ignore[return-value]
            'status': 'success',
            'modal': value
        })

    def handle_get_bluetooth_settings(self) -> Union["Response", tuple["Response", int]]:
        """Handle GET request for bluetooth settings.

        Returns:
            Flask JSON response with Bluetooth settings
        """
        try:
            settings: Dict[str, Any] = cast(
                Dict[str, Any], get_bluetooth_settings()
            )  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': settings
            })
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting bluetooth settings: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to retrieve bluetooth settings",
                "error": str(e),
            }), 500

    def handle_set_bluetooth_settings(self) -> Union["Response", tuple["Response", int]]:
        """Handle POST request for bluetooth settings.

        Returns:
            Flask JSON response with updated settings
        """
        try:
            settings: Dict[str, Any] = cast(
                Dict[str, Any], set_bluetooth_settings(request.args)  # type: ignore[arg-type]
            )
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': settings
            })
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error setting bluetooth settings: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to set bluetooth settings",
                "error": str(e),
            }), 500

    def handle_get_paired_devices(self) -> Union["Response", tuple["Response", int]]:
        """Handle GET request for paired devices.

        Returns:
            Flask JSON response with list of paired devices
        """
        try:
            devices: Any = get_paired_devices()  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': devices
            })
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting paired devices: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": "Failed to retrieve paired devices",
                "error": str(e),
            }), 500

    def handle_unpair_device(self) -> Union["Response", tuple["Response", int]]:
        """Handle POST request to unpair a device.

        Retrieves device address from request args and unpairing device.

        Returns:
            Flask JSON response indicating success or error
        """
        try:
            address: Optional[str] = request.args.get("address")
            result: Any = unpair_device(address)  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': result
            })
        except ValueError as e:
            logger.error("Error unpairing device: %s", e)
            return jsonify({  # type: ignore[return-value]
                "status": "error",
                "message": str(e),
            }), 400
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error unpairing device: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to unpair device",
                "error": str(e),
            }), 500
