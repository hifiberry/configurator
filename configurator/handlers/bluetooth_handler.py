import logging
from flask import jsonify, request
from ..bluetooth import get_bluetooth_settings, set_bluetooth_settings, get_paired_devices, unpair_device

logger = logging.getLogger(__name__)

class BluetoothHandler:
    """Handler for bluetooth configuration API endpoints"""
    passkey=None
    show_modal=None

    def __init__(self):
        """Initialize the bluetooth handler"""
        self.passkey = None
        pass

    def handle_get_bluetooth_passkey(self):
        """Return the stored passkey and delete it afterwards."""
        value = self.passkey
        self.passkey = None
        return jsonify({
            'status': 'success',
            'passkey': value
        })
    
    def handle_set_bluetooth_passkey(self):
        """Store the provided Bluetooth passkey."""
        try:
            pk = request.args.get("passkey") or request.json.get("passkey")

            if not pk:
                return jsonify({
                    'status': 'error',
                    'message': 'No passkey provided'
                }), 400

            self.passkey = pk

            return jsonify({
                'status': 'success',
                'message': 'Passkey stored successfully'
            })

        except Exception as e:
            logger.error(f"Error setting Bluetooth passkey: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to store passkey',
                'error': str(e)
            }), 500

    def handle_set_show_modal(self):
        """Store a modal request payload or identifier."""
        try:
            modal = request.args.get("modal") or request.json.get("modal")

            if not modal:
                return jsonify({
                    'status': 'error',
                    'message': 'No modal value provided'
                }), 400

            self.show_modal = modal

            return jsonify({
                'status': 'success',
                'message': 'Modal request stored successfully'
            })

        except Exception as e:
            logger.error(f"Error setting modal: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to store modal request',
                'error': str(e)
            }), 500

    def handle_get_show_modal(self):
        """Return the stored modal request and clear it."""
        value = self.show_modal
        self.show_modal = None
        return jsonify({
            'status': 'success',
            'modal': value
        })

    def handle_get_bluetooth_settings(self):
        """Handle GET request for bluetooth settings."""
        try:
            settings = get_bluetooth_settings()
            return jsonify({
                'status': 'success',
                'data': settings
            })
        except Exception as e:
            logger.error(f"Error getting bluetooth settings: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to retrieve bluetooth settings',
                'error': str(e)
            }), 500

    def handle_set_bluetooth_settings(self):
        """Handle POST request for bluetooth settings."""
        try:
            settings = set_bluetooth_settings(request.args)
            return jsonify({
                'status': 'success',
                'data': settings
            })
        except Exception as e:
            logger.error(f"Error setting bluetooth settings: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to set bluetooth settings',
                'error': str(e)
            }), 500

    def handle_get_paired_devices(self):
        """Handle GET request for paired devices."""
        try:
            devices = get_paired_devices()
            return jsonify({
                'status': 'success',
                'data': devices
            })
        except Exception as e:
            logger.error(f"Error getting paired devices: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to retrieve paired devices',
                'error': str(e)
            }), 500

    def handle_unpair_device(self):
        """Handle POST request to unpair a device."""
        try:
            address = request.args.get("address")
            result = unpair_device(address)
            return jsonify({
                'status': 'success',
                'data': result
            })
        except ValueError as e:
            logger.error(f"Error unpairing device: {e}")
            return jsonify({
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
