#!/usr/bin/env python3
"""Make a freshly installed extension visible to a *running* config-server.

An extension deb ships /etc/configserver/conf.d/<ext>.json to grant the Web UI
permission to control its service, and the systemd service map has to take in
the unit the deb just installed.

Restarting config-server is not an option here: it would kill the job the UI is
polling. So we refresh in place instead. ConfigParser now notices a changed
conf.d by itself, so the config reload is no longer what makes a new permission
visible -- it just makes it visible at a defined point, before the job reports
success, rather than on the next read.

Every step is best-effort and independent: one failure must not strand the
others, because a half-refreshed system is what produces the confusing
"installed but can't start it" state.
"""

import logging
from typing import Callable, List, Optional

from ..config_parser import reload_config as _default_reload_config

logger = logging.getLogger(__name__)


def refresh_system_state(service_manager=None,
                         config_reloader: Optional[Callable[[], object]] = None
                         ) -> List[str]:
    """Refresh cached state after an install/uninstall.

    Returns the names of the steps that completed successfully.
    """
    config_reloader = config_reloader or _default_reload_config
    completed = []

    if service_manager is not None:
        try:
            ok, message = service_manager.daemon_reload()
            if ok:
                completed.append("daemon-reload")
            else:
                logger.warning(f"daemon-reload failed: {message}")
        except Exception as e:
            logger.warning(f"daemon-reload raised: {e}")

    try:
        config_reloader()
        completed.append("reload-config")
    except Exception as e:
        logger.warning(f"config reload raised: {e}")

    if service_manager is not None:
        try:
            service_manager.refresh_service_map()
            completed.append("rescan-services")
        except Exception as e:
            logger.warning(f"service rescan raised: {e}")

    logger.info(f"Refreshed system state after extension change: {completed}")
    return completed
