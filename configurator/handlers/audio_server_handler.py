#!/usr/bin/env python3

import logging

try:
    from flask import jsonify, request
except ImportError:
    jsonify = None
    request = None

from .. import audio_server

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
