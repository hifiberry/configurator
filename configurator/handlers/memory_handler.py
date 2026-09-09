#!/usr/bin/env python3
"""
HiFiBerry Configuration API Memory Handler

Serves the per-feature memory report. Read-only.
"""

import logging

try:
    from flask import request, jsonify
except ImportError:
    request = None
    jsonify = None

from ..memoryinfo import MemoryInfo

logger = logging.getLogger(__name__)


class MemoryHandler:
    """Handler for the memory usage report"""

    def __init__(self, memory_info=None):
        self.memory_info = memory_info or MemoryInfo()

    def get_report(self, include_processes: bool):
        """Collect the report. Returns (payload, status) with no Flask involved,
        so it is testable without an app context."""
        try:
            return self.memory_info.collect(include_processes=include_processes), 200
        except Exception as e:
            logger.error("Failed to collect memory report: %s", e)
            return {'status': 'error', 'message': str(e)}, 503

    def handle_get_memory(self):
        include_processes = request.args.get('processes', '0') in ('1', 'true', 'yes')
        payload, status = self.get_report(include_processes)
        return jsonify(payload), status
