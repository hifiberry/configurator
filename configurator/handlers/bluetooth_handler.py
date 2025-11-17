import logging
from flask import jsonify, request
from ..bluetooth import get_bluetooth_settings, set_bluetooth_settings, get_paired_devices, unpair_device

logger = logging.getLogger(__name__)

class BluetoothHandler:
    """Handler for bluetooth configuration API endpoints"""

    def __init__(self):
        """Initialize the bluetooth handler"""
        pass

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
