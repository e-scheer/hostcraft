"""Background sampler that persists realtime stats to the DB.

Runs in a daemon thread inside the same process as Daphne. Sampling happens
every PERF_SAMPLE_INTERVAL seconds (default 30 s); old samples are pruned to
keep the table bounded (default 7 days = ~20k rows).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import timedelta

from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


SAMPLE_INTERVAL_SEC = int(os.getenv("PERF_SAMPLE_INTERVAL", "30"))
RETENTION_DAYS = int(os.getenv("PERF_RETENTION_DAYS", "7"))
CLEANUP_EVERY_SEC = 3600  # once an hour


_started = False


def start_collector() -> None:
    """Idempotent — only spawns the thread once per process."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_run, daemon=True, name="perf-collector").start()
    logger.info("perf collector started (interval=%ss, retention=%sd)", SAMPLE_INTERVAL_SEC, RETENTION_DAYS)


def is_main_serving_process() -> bool:
    """True when we're the actual Django/Daphne worker, not a one-shot
    management command (migrate, makemigrations, shell, ...) and not the
    runserver autoreload watcher parent."""
    argv = " ".join(sys.argv)
    if "runserver" in argv:
        return os.environ.get("RUN_MAIN") == "true"
    if any(t in argv for t in ("daphne", "gunicorn", "asgi", "wsgi")):
        return True
    return False


def _run() -> None:
    last_cleanup = 0.0
    while True:
        try:
            _sample_once()
        except Exception:  # noqa: BLE001
            logger.exception("perf sample failed")
        finally:
            close_old_connections()

        now = time.monotonic()
        if now - last_cleanup > CLEANUP_EVERY_SEC:
            try:
                _cleanup()
            except Exception:  # noqa: BLE001
                logger.exception("perf cleanup failed")
            finally:
                close_old_connections()
            last_cleanup = now

        time.sleep(SAMPLE_INTERVAL_SEC)


def _sample_once() -> None:
    # Local imports keep `apps.ready()` lean and avoid circular imports.
    from . import realtime
    from .models import PerfSample

    snap = realtime.snapshot()
    with transaction.atomic():
        PerfSample.objects.create(
            cpu_percent=snap.get("cpu_percent"),
            memory_used=snap.get("memory_used"),
            memory_limit=snap.get("memory_limit"),
            players_online=snap.get("players_online"),
            players_max=snap.get("players_max"),
            tps_1m=(snap.get("tps") or [None])[0],
        )


def _cleanup() -> None:
    from .models import PerfSample

    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    deleted, _ = PerfSample.objects.filter(t__lt=cutoff).delete()
    if deleted:
        logger.info("perf cleanup removed %s old samples", deleted)
