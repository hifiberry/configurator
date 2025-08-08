#!/usr/bin/env python3

import logging
from flask import jsonify, request
from typing import Dict, Any
from ..i2c import get_i2c_info

logger = logging.getLogger(__name__)


class I2CHandler:
    """Handler for I2C device scanning API endpoints"""
    
    def __init__(self):
        """Initialize the I2C handler"""
        pass
    
    def handle_get_i2c_devices(self) -> Dict[str, Any]:
        """
        Handle GET request for I2C device scan.
        
        Returns:
            Flask response with I2C device scan data
        """
        try:
            # Get bus number from query parameter, default to 1
            bus_number = request.args.get('bus', default=1, type=int)
            
            # Validate bus number
            if bus_number < 0 or bus_number > 10:
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid bus number. Must be between 0 and 10.'
                }), 400
            
            i2c_info = get_i2c_info(bus_number)
            return jsonify({
                'status': 'success' if 'error' not in i2c_info else 'error',
                'data': i2c_info
            })
        except Exception as e:
            logger.error(f"Error scanning I2C devices: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to scan I2C devices',
                'error': str(e)
            }), 500
