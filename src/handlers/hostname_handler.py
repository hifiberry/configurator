#!/usr/bin/env python3
"""HTTP handler for hostname read/write endpoints."""

import logging
import traceback
from typing import Any, Union

try:
    from flask import jsonify, request
except ImportError:
    # Flask not available - likely during testing or installation
    jsonify = None
    request = None

from ..hostname_utils import (
    get_hostnames_with_fallback,
    sanitize_hostname,
    validate_hostname,
    validate_pretty_hostname,
    set_pretty_hostname
)
from ..hostconfig import set_hostname_with_hosts_update

logger = logging.getLogger(__name__)


class HostnameHandler:
    """Handler for hostname related API endpoints."""

    def __init__(self) -> None:
        """Initialize the hostname handler."""
        logger.debug("Initializing HostnameHandler")

    def handle_get_hostname(self) -> Union[tuple[Any, int], Any]:
        """
        Handle GET /api/v1/hostname
        Get current system and pretty hostnames
        """
        try:
            logger.debug("Getting current hostnames")

            hostname, pretty_hostname = get_hostnames_with_fallback()

            if hostname is None:
                if jsonify:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to retrieve hostname information'
                    }), 500
                return {'status': 'error', 'message': 'Failed to retrieve hostname information'}

            if jsonify:
                return jsonify({
                    'status': 'success',
                    'data': {
                        'hostname': hostname,
                        'pretty_hostname': pretty_hostname
                    }
                })
            return {
                'status': 'success',
                'data': {
                    'hostname': hostname,
                    'pretty_hostname': pretty_hostname
                }
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting hostname: %s", e)
            logger.debug(traceback.format_exc())
            if jsonify:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to get hostname',
                    'error': str(e)
                }), 500
            return {
                'status': 'error',
                'message': 'Failed to get hostname',
                'error': str(e)
            }

    def handle_set_hostname(self) -> Union[tuple[Any, int], Any]:
        # pylint: disable=too-many-return-statements,too-many-branches
        """
        Handle POST /api/v1/hostname
        Set system hostname (and optionally pretty hostname)
        """
        try:
            # Get JSON data from request
            if not request or not request.is_json:
                if jsonify:
                    return jsonify({
                        'status': 'error',
                        'message': 'Content-Type must be application/json'
                    }), 400
                return {
                    'status': 'error',
                    'message': 'Content-Type must be application/json'
                }

            data = request.get_json()
            if not data:
                if jsonify:
                    return jsonify({
                        'status': 'error',
                        'message': 'Missing request body'
                    }), 400
                return {
                    'status': 'error',
                    'message': 'Missing request body'
                }

            hostname = data.get('hostname')
            pretty_hostname = data.get('pretty_hostname')

            # Must provide at least one
            if not hostname and not pretty_hostname:
                if jsonify:
                    return jsonify({
                        'status': 'error',
                        'message': 'Must provide either hostname or pretty_hostname'
                    }), 400
                return {
                    'status': 'error',
                    'message': 'Must provide either hostname or pretty_hostname'
                }

            # If pretty hostname provided, derive regular hostname from it
            if pretty_hostname:
                if not validate_pretty_hostname(pretty_hostname):
                    if jsonify:
                        return jsonify({
                            'status': 'error',
                            'message': 'Invalid pretty hostname format'
                        }), 400
                    return {
                        'status': 'error',
                        'message': 'Invalid pretty hostname format'
                    }

                # Derive hostname from pretty hostname if not explicitly provided
                if not hostname:
                    hostname = sanitize_hostname(pretty_hostname)

            # Validate hostname
            if hostname and not validate_hostname(hostname):
                invalid_hostname_message = (
                    'Invalid hostname format (max 64 chars, '
                    'ASCII letters/numbers/hyphens, '
                    'no leading/trailing hyphens)'
                )
                if jsonify:
                    return jsonify({
                        'status': 'error',
                        'message': invalid_hostname_message
                    }), 400
                return {
                    'status': 'error',
                    'message': invalid_hostname_message
                }

            logger.debug(
                "Setting hostnames - hostname: %s, pretty: %s",
                hostname,
                pretty_hostname,
            )

            # Set the hostnames
            success = True

            if hostname:
                if not set_hostname_with_hosts_update(hostname):
                    success = False

            if pretty_hostname and success:
                if not set_pretty_hostname(pretty_hostname):
                    success = False

            if success:
                # Get updated hostnames to return
                new_hostname, new_pretty = get_hostnames_with_fallback()

                if jsonify:
                    return jsonify({
                        'status': 'success',
                        'message': 'Hostname updated successfully',
                        'data': {
                            'hostname': new_hostname,
                            'pretty_hostname': new_pretty
                        }
                    })
                return {
                    'status': 'success',
                    'message': 'Hostname updated successfully',
                    'data': {
                        'hostname': new_hostname,
                        'pretty_hostname': new_pretty
                    }
                }
            if jsonify:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to update hostname'
                }), 500
            return {
                'status': 'error',
                'message': 'Failed to update hostname'
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error setting hostname: %s", e)
            logger.debug(traceback.format_exc())
            if jsonify:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set hostname',
                    'error': str(e)
                }), 500
            return {
                'status': 'error',
                'message': 'Failed to set hostname',
                'error': str(e)
            }
