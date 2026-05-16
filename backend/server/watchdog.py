"""Auto-restart the Minecraft container when it goes unhealthy.

`itzg/minecraft-server` ships with a Docker HEALTHCHECK that pings RCON. If
the server deadlocks or RCON stops responding, Docker flips `Health.Status`
to `unhealthy` even though the process technically still runs. Plain
`restart: unless-stopped` doesn't catch that case — only outright crashes.

This watchdog polls the health every 30s and restarts when:
  • the container is `running` AND
  • Health.Status is `unhealthy` AND
  • it's been unhealthy for `threshold_seconds` consecutive checks AND
  • we haven't restarted more than `max_restarts_per_hour` times recently.

The cooldown protects against a degenerate boot loop where restarting only
buys 30s before the next unhealthy reading.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


POLL_INTERVAL_SEC = 30
DEFAULT_THRESHOLD_SEC = 120  # 4 consecutive unhealthy polls

_started = False
_recent_restarts: deque[float] = deque()  # unix-seconds of recent auto-restarts


def start_watchdog() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_run, daemon=True, name="server-watchdog").start()
    logger.info("server watchdog started")


def is_main_serving_process() -> bool:
    argv = " ".join(sys.argv)
    if "runserver" in argv:
        return os.environ.get("RUN_MAIN") == "true"
    if any(t in argv for t in ("daphne", "gunicorn", "asgi", "wsgi")):
        return True
    return False


def _run() -> None:
    unhealthy_since: float | None = None
    while True:
        try:
            unhealthy_since = _tick(unhealthy_since)
        except Exception:  # noqa: BLE001
            logger.exception("watchdog tick crashed")
        finally:
            close_old_connections()
        time.sleep(POLL_INTERVAL_SEC)


def _tick(unhealthy_since: float | None) -> float | None:
    from .models_watchdog import WatchdogConfig
    from . import docker_client

    cfg = WatchdogConfig.current()
    if not cfg.enabled:
        return None

    try:
        container = docker_client._get_container()
    except Exception:  # noqa: BLE001
        return unhealthy_since

    state = container.attrs.get("State", {}) or {}
    status = state.get("Status")
    health = (state.get("Health") or {}).get("Status")

    # Only track unhealthy when actually running. Stopped/exited is handled
    # by Docker's restart_policy.
    if status != "running" or health != "unhealthy":
        return None

    now = time.monotonic()
    if unhealthy_since is None:
        unhealthy_since = now
        logger.info("watchdog: container reported unhealthy, starting timer")
        return unhealthy_since

    if (now - unhealthy_since) < cfg.threshold_seconds:
        return unhealthy_since

    # Threshold reached — apply rate limit.
    _trim_old(_recent_restarts, seconds=3600)
    if len(_recent_restarts) >= cfg.max_restarts_per_hour:
        logger.warning(
            "watchdog: rate-limited (%s restarts in last hour ≥ max=%s)",
            len(_recent_restarts),
            cfg.max_restarts_per_hour,
        )
        return unhealthy_since  # keep counting; we'll retry once the window slides

    logger.warning("watchdog: restarting unhealthy MC container")
    try:
        container.restart(timeout=60)
        _recent_restarts.append(time.time())
        with transaction.atomic():
            cfg.last_restart_at = datetime.now(timezone.utc)
            cfg.total_restarts = (cfg.total_restarts or 0) + 1
            cfg.save(update_fields=["last_restart_at", "total_restarts"])
        # Log to AuditLog so it surfaces in the dashboard activity feed.
        _record_audit_entry()
    except Exception as exc:  # noqa: BLE001
        logger.exception("watchdog restart failed: %s", exc)

    return None  # reset, we just restarted


def _trim_old(buf: deque[float], *, seconds: int) -> None:
    cutoff = time.time() - seconds
    while buf and buf[0] < cutoff:
        buf.popleft()


def _record_audit_entry() -> None:
    try:
        from audit.models import AuditLog

        AuditLog.objects.create(
            user=None,
            action="server.watchdog.restart",
            method="AUTO",
            target="watchdog",
            payload={"reason": "unhealthy"},
            status_code=200,
            status=AuditLog.Status.SUCCESS,
        )
    except Exception:  # noqa: BLE001
        logger.exception("watchdog: failed to write audit entry")
