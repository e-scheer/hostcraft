"""Background scheduler thread.

Polls every TICK_INTERVAL seconds and runs schedules whose previous cron fire
is more recent than their last successful run.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime, timezone

from croniter import croniter
from django.db import close_old_connections

from .models import Schedule
from .runners import HANDLERS

logger = logging.getLogger(__name__)


TICK_INTERVAL = 30  # seconds — granularity of cron firings we'll honor


_thread: threading.Thread | None = None


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run_forever, name="hostcraft-scheduler", daemon=True)
    _thread.start()
    logger.info("scheduler thread started")


def _run_forever() -> None:
    while True:
        try:
            tick(datetime.now(tz=timezone.utc))
        except Exception:  # noqa: BLE001
            logger.exception("scheduler tick crashed")
        finally:
            close_old_connections()
        time.sleep(TICK_INTERVAL)


def tick(now: datetime) -> None:
    """Fire any schedule whose previous cron firing was missed."""
    for sched in Schedule.objects.filter(enabled=True):
        try:
            if not _is_due(sched, now):
                continue
            _execute(sched, now)
        except Exception:  # noqa: BLE001 — never let one schedule kill the loop
            logger.exception("scheduler: schedule %s failed to evaluate", sched.pk)


def next_fire(cron_expr: str, after: datetime) -> datetime | None:
    try:
        return croniter(cron_expr, after).get_next(datetime)
    except (ValueError, KeyError):
        return None


def previous_fire(cron_expr: str, before: datetime) -> datetime | None:
    try:
        return croniter(cron_expr, before).get_prev(datetime)
    except (ValueError, KeyError):
        return None


def _is_due(sched: Schedule, now: datetime) -> bool:
    prev = previous_fire(sched.cron, now)
    if prev is None:
        return False
    if sched.last_run_at is None:
        # Never ran — fire only if a cron firing happened since this schedule
        # was created (avoid backfiring everything when the panel boots).
        return prev >= sched.created_at
    return prev > sched.last_run_at


def _execute(sched: Schedule, now: datetime) -> None:
    handler = HANDLERS.get(sched.kind)
    if handler is None:
        sched.last_status = Schedule.LastStatus.FAILED
        sched.last_error = f"Unknown kind: {sched.kind}"
        sched.last_run_at = now
        sched.save(update_fields=["last_status", "last_error", "last_run_at"])
        return

    sched.last_status = Schedule.LastStatus.RUNNING
    sched.last_run_at = now
    sched.save(update_fields=["last_status", "last_run_at"])

    try:
        handler(sched.payload or {})
        sched.last_status = Schedule.LastStatus.SUCCESS
        sched.last_error = ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("schedule %s failed", sched.pk)
        sched.last_status = Schedule.LastStatus.FAILED
        sched.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:1500]}"
    sched.save(update_fields=["last_status", "last_error"])
