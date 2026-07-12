import logging
from typing import Any, Dict, Optional, Union, cast
from flask import jsonify, request, Response
from ..bluetooth import get_bluetooth_settings, set_bluetooth_settings, get_paired_devices, unpair_device  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

class BluetoothHandler:
    """Handler for bluetooth configuration API endpoints"""
    passkey: Optional[str] = None
    show_modal: Optional[str] = None

    def __init__(self) -> None:
        """Initialize the bluetooth handler"""
        self.passkey: Optional[str] = None
        self.show_modal: Optional[str] = None

    def handle_get_bluetooth_passkey(self) -> 'Union[Response, tuple[Response, int]]':
        """Return the stored passkey and delete it afterwards."""
        value: Optional[str] = self.passkey
        self.passkey = None
        return jsonify({  # type: ignore[return-value]
            'status': 'success',
            'passkey': value
        })
    
    def handle_set_bluetooth_passkey(self) -> 'Union[Response, tuple[Response, int]]':
        """Store the provided Bluetooth passkey."""
        try:
            pk: Optional[str] = request.args.get("passkey") or (request.json.get("passkey") if request.is_json else None)  # type: ignore[union-attr]

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

        except Exception as e:
            logger.error(f"Error setting Bluetooth passkey: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to store passkey',
                'error': str(e)
            }), 500

    def handle_set_show_modal(self) -> 'Union[Response, tuple[Response, int]]':
        """Store a modal request payload or identifier."""
        try:
            modal: Optional[str] = request.args.get("modal") or (request.json.get("modal") if request.is_json else None)  # type: ignore[union-attr]

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

        except Exception as e:
            logger.error(f"Error setting modal: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to store modal request',
                'error': str(e)
            }), 500

    def handle_get_show_modal(self) -> 'Union[Response, tuple[Response, int]]':
        """Return the stored modal request and clear it."""
        value: Optional[str] = self.show_modal
        self.show_modal = None
        return jsonify({  # type: ignore[return-value]
            'status': 'success',
            'modal': value
        })

    def handle_get_bluetooth_settings(self) -> 'Union[Response, tuple[Response, int]]':
        """Handle GET request for bluetooth settings."""
        try:
            settings: Dict[str, Any] = cast(Dict[str, Any], get_bluetooth_settings())  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': settings
            })
        except Exception as e:
            logger.error(f"Error getting bluetooth settings: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to retrieve bluetooth settings',
                'error': str(e)
            }), 500

    def handle_set_bluetooth_settings(self) -> 'Union[Response, tuple[Response, int]]':
        """Handle POST request for bluetooth settings."""
        try:
            settings: Dict[str, Any] = cast(Dict[str, Any], set_bluetooth_settings(request.args))  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': settings
            })
        except Exception as e:
            logger.error(f"Error setting bluetooth settings: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to set bluetooth settings',
                'error': str(e)
            }), 500

    def handle_get_paired_devices(self) -> 'Union[Response, tuple[Response, int]]':
        """Handle GET request for paired devices."""
        try:
            devices: Any = get_paired_devices()  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': devices
            })
        except Exception as e:
            logger.error(f"Error getting paired devices: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to retrieve paired devices',
                'error': str(e)
            }), 500

    def handle_unpair_device(self) -> 'Union[Response, tuple[Response, int]]':
        """Handle POST request to unpair a device."""
        try:
            address: Optional[str] = request.args.get("address")
            result: Any = unpair_device(address)  # type: ignore[arg-type]
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': result
            })
        except ValueError as e:
            logger.error(f"Error unpairing device: {e}")
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': str(e),
            }), 400
        except Exception as e:
            logger.error(f"Error unpairing device: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to unpair device',
                'error': str(e)
            }), 500
