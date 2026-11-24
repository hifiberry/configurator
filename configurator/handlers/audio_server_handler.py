#!/usr/bin/env python3

import logging

try:
    from flask import jsonify, request
except ImportError:
    jsonify = None
    request = None

from .. import aas_settings, audio_server

logger = logging.getLogger(__name__)


class AudioServerHandler:
    """Handler for the audio server (PipeWire or aas) API endpoints"""

    def handle_get(self):
        """GET /api/v1/audio-server"""
        try:
            return jsonify({'status': 'success', 'data': audio_server.get()})
        except Exception as e:
            logger.error(f"Error reading the audio server: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_set(self):
        """POST /api/v1/audio-server with {"server": "pipewire"|"aas"}"""
        body = request.get_json(silent=True)
        server = body.get('server') if isinstance(body, dict) else None
        if server not in audio_server.SERVERS:
            return jsonify({
                'status': 'error',
                'message': 'server must be "pipewire" or "aas"'
            }), 400
        try:
            data = audio_server.set_server(server)
        except audio_server.AudioServerUnavailable as e:
            return jsonify({'status': 'error', 'message': str(e)}), 409
        except audio_server.AudioServerError as e:
            logger.error(f"Setting the audio server failed: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
        except Exception as e:
            logger.error(f"Error setting the audio server: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
        return jsonify({'status': 'success', 'data': data})

    def handle_get_aas_settings(self):
        """GET /api/v1/audio-server/aas-settings"""
        try:
            return jsonify({'status': 'success', 'data': aas_settings.get()})
        except aas_settings.AasSettingsFileError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 409
        except Exception as e:
            logger.error(f"Error reading the aas settings: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def handle_set_aas_settings(self):
        """POST /api/v1/audio-server/aas-settings with {"latency_ms": 1..100 | null}"""
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or 'latency_ms' not in body:
            return jsonify({
                'status': 'error',
                'message': 'latency_ms must be given, an integer from 1 to 100 or null'
            }), 400
        try:
            data = aas_settings.set_latency(body['latency_ms'])
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except aas_settings.AasSettingsFileError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 409
        except Exception as e:
            logger.error(f"Error setting the aas settings: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
        return jsonify({'status': 'success', 'data': data})
