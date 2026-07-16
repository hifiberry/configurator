#!/usr/bin/env python3
"""Make a freshly installed extension visible to a *running* config-server.

An extension deb ships /etc/configserver/conf.d/<ext>.json to grant the Web UI
permission to control its service. ConfigParser caches the merged conf.d config
at startup, so without this the new permission is invisible until a restart --
the long-standing "restart config-server after installing a player" gotcha.

Restarting is not an option here: it would kill the job the UI is polling. So
we reload in place instead, which fixes the install path and the underlying
bug at once.

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
