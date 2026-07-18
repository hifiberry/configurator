#!/usr/bin/env python3
"""HTTP handler for network configuration endpoint."""

import logging
from typing import Any, Dict, TYPE_CHECKING, Union, cast

from ..network import get_network_config

# Type alias for network config
NetworkConfig = Dict[str, Any]

if TYPE_CHECKING:
    from flask import Response
else:
    Response = Any

try:
    from flask import jsonify
except ImportError:
    # Flask is optional - only needed when running with Flask
    def jsonify(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        """Stub jsonify when Flask is not installed."""
        raise RuntimeError("Flask is not installed")

logger = logging.getLogger(__name__)


class NetworkHandler:  # pylint: disable=too-few-public-methods
    """Handler for network configuration API endpoints."""

    def handle_get_network_config(self) -> Union["Response", tuple["Response", int]]:
        """
        Handle GET request for network configuration.

        Returns:
            Flask response with network configuration data
        """
        try:
            config: NetworkConfig = cast(NetworkConfig, get_network_config())
            return jsonify({  # type: ignore[return-value]
                'status': 'success',
                'data': config
            })
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting network configuration: %s", e)
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to retrieve network configuration',
                'error': str(e)
            }), 500
