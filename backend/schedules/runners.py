"""One handler per Schedule kind. Each returns nothing on success, raises on failure."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_restart(_payload: dict[str, Any]) -> None:
    from server import docker_client
    docker_client.restart(timeout=int(_payload.get("timeout", 60) or 60))


def run_backup_world(payload: dict[str, Any]) -> None:
    _trigger_backup("world", payload)


def run_backup_full(payload: dict[str, Any]) -> None:
    _trigger_backup("full", payload)


def run_rcon(payload: dict[str, Any]) -> None:
    from server import rcon
    command = (payload.get("command") or "").strip()
    if not command:
        raise ValueError("RCON command is empty")
    reply = rcon.send(command)
    logger.info("scheduled rcon %s -> %s", command, reply[:200])


def _trigger_backup(kind: str, payload: dict[str, Any]) -> None:
    from backups.models import Backup
    from backups import service

    prefix = (payload.get("name_prefix") or "scheduled").strip() or "scheduled"
    name = f"{prefix}-{kind}-{_now_stamp()}"
    backup = Backup.objects.create(name=name, kind=kind, status=Backup.Status.PENDING)
    service.trigger(backup)


HANDLERS: dict[str, callable] = {
    "restart": run_restart,
    "backup_world": run_backup_world,
    "backup_full": run_backup_full,
    "rcon": run_rcon,
}
