#!/usr/bin/env python3

import logging
from flask import jsonify
from typing import Dict, Any
from ..network import get_network_config

logger = logging.getLogger(__name__)


class NetworkHandler:
    """Handler for network configuration API endpoints"""
    
    def __init__(self):
        """Initialize the network handler"""
        pass
    
    def handle_get_network_config(self) -> Dict[str, Any]:
        """
        Handle GET request for network configuration.
        
        Returns:
            Flask response with network configuration data
        """
        try:
            config = get_network_config()
            return jsonify(config)
        except Exception as e:
            logger.error(f"Error getting network configuration: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to retrieve network configuration',
                'error': str(e)
            }), 500
