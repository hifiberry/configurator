#!/usr/bin/env python3
"""HTTP handler for I2C device scan endpoint."""

import logging
from typing import Any, TYPE_CHECKING, Union

from ..i2c import get_i2c_info

if TYPE_CHECKING:
    from flask import Response
else:
    Response = Any

try:
    from flask import jsonify, request
except ImportError:
    # Flask is optional - only needed when running with Flask
    def jsonify(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        """Stub jsonify when Flask is not installed."""
        raise RuntimeError("Flask is not installed")

    class StubArgs:  # pylint: disable=too-few-public-methods
        """Stub request args object when Flask is unavailable."""

        def get(self, _key: str, default: Any = None, type: Any = None) -> Any:  # pylint: disable=redefined-builtin
            """Return default value for missing key."""
            if type is not None and default is not None:
                try:
                    return type(default)
                except (TypeError, ValueError):
                    return default
            return default

    class StubRequest:  # pylint: disable=too-few-public-methods
        """Stub request object when Flask is unavailable."""

        args: StubArgs = StubArgs()

    request = StubRequest()  # type: ignore

logger = logging.getLogger(__name__)


class I2CHandler:  # pylint: disable=too-few-public-methods
    """Handler for I2C device scanning API endpoints."""

    def handle_get_i2c_devices(self) -> Union["Response", tuple["Response", int]]:
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
                return jsonify({  # type: ignore[return-value]
                    'status': 'error',
                    'message': 'Invalid bus number. Must be between 0 and 10.'
                }), 400

            i2c_info = get_i2c_info(bus_number)
            return jsonify({  # type: ignore[return-value]
                'status': 'success' if 'error' not in i2c_info else 'error',
                'data': i2c_info
            })
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error scanning I2C devices: %s", e)
            return jsonify({  # type: ignore[return-value]
                'status': 'error',
                'message': 'Failed to scan I2C devices',
                'error': str(e)
            }), 500
