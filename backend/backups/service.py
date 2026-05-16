"""Backup execution.

Backups run in a daemon thread so the HTTP request that triggered them returns
immediately. The frontend polls /api/backups/ to see when status flips from
`running` to `ready`. SQLite serializes writes (timeout=20s in settings), so
two simultaneous backups will queue at the DB level — they won't corrupt.
"""

from __future__ import annotations

import logging
import tarfile
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction

from .models import Backup

logger = logging.getLogger(__name__)


def trigger(backup: Backup) -> None:
    """Schedule a backup to run in a background thread."""
    threading.Thread(target=_run, args=(backup.pk,), daemon=True).start()


def trigger_upload(backup_pk: int, destination_pk: int) -> None:
    """Schedule a backup upload to a remote destination in a background thread."""
    threading.Thread(target=_run_upload, args=(backup_pk, destination_pk), daemon=True).start()


def trigger_restore(backup_pk: int) -> None:
    """Schedule a restore in a background thread.

    The restore is deliberately async: it stops the MC container, creates an
    automatic safety backup of the current world, deletes the target world
    folders, extracts the chosen archive, and restarts the container — that
    can take 30s–2min depending on world size, so we don't make the HTTP
    request hang.
    """
    threading.Thread(target=_run_restore, args=(backup_pk,), daemon=True).start()


def _run_restore(backup_pk: int) -> None:
    """End-to-end restore. Updates Backup.restore_status as it goes."""
    from datetime import datetime, timezone as tz
    import shutil
    import tarfile
    from server import docker_client

    try:
        backup = Backup.objects.get(pk=backup_pk)
    except Backup.DoesNotExist:
        return

    if backup.status != Backup.Status.READY or not backup.path:
        logger.error("restore: backup not ready (id=%s)", backup_pk)
        return

    archive = Path(backup.path)
    if not archive.is_file():
        with transaction.atomic():
            backup.restore_status = Backup.RestoreStatus.FAILED
            backup.restore_error = f"Archive missing on disk: {archive}"
            backup.save(update_fields=["restore_status", "restore_error"])
        close_old_connections()
        return

    with transaction.atomic():
        backup.restore_status = Backup.RestoreStatus.RUNNING
        backup.restore_error = ""
        backup.save(update_fields=["restore_status", "restore_error"])

    data_root = Path(settings.MC_DATA_PATH).resolve()
    was_running = False

    try:
        # 1) Stop the MC container if it's running. The world is locked
        #    by Paper while it's up, so we can't safely overwrite it.
        try:
            c = docker_client._get_container()
            was_running = c.status == "running"
            if was_running:
                logger.info("restore: stopping MC container")
                c.stop(timeout=60)
        except Exception as exc:  # noqa: BLE001 — never block on docker hiccups
            logger.warning("restore: stop step failed but continuing: %s", exc)

        # 2) Take a safety snapshot of the current state (same kind as the
        #    archive being restored). If this fails we abort so the user
        #    never loses data.
        ts = datetime.now(tz.utc).strftime("%Y%m%d-%H%M%S")
        safety = Backup.objects.create(
            name=f"safety-before-restore-{ts}",
            kind=backup.kind,
            status=Backup.Status.PENDING,
        )
        _run(safety.pk)  # synchronous: same thread, no spawn
        safety.refresh_from_db()
        if safety.status != Backup.Status.READY:
            raise RuntimeError(f"safety backup failed: {safety.error[:200]}")

        # 3) Wipe the target directories so stale files don't survive.
        #    For kind=world we only nuke the worlds; full backups overwrite
        #    everything via tar's natural overwrite (we don't rm /mc-data —
        #    too aggressive).
        if backup.kind == Backup.Kind.WORLD:
            for d in sources_for_kind(backup.kind):
                if d.exists() and d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)

        # 4) Extract. `filter='data'` (Python 3.12+) refuses path traversal,
        #    absolute paths, symlinks pointing outside, and setuid bits.
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(data_root, filter="data")

        # 5) Restart the container if we stopped it.
        if was_running:
            try:
                c = docker_client._get_container()
                c.start()
                logger.info("restore: container restarted")
            except Exception as exc:  # noqa: BLE001
                logger.warning("restore: restart failed: %s", exc)

        with transaction.atomic():
            backup.restore_status = Backup.RestoreStatus.DONE
            backup.restored_at = datetime.now(tz.utc)
            backup.save(update_fields=["restore_status", "restored_at"])
        logger.info("restore: %s done", backup.name)

    except Exception as exc:  # noqa: BLE001 — surface anything to UI
        logger.exception("restore failed")
        with transaction.atomic():
            backup.restore_status = Backup.RestoreStatus.FAILED
            backup.restore_error = f"{type(exc).__name__}: {exc}"
            backup.save(update_fields=["restore_status", "restore_error"])
    finally:
        close_old_connections()


def _run_upload(backup_pk: int, destination_pk: int) -> None:
    """Push a ready backup to its destination. Updates remote_status as it goes."""
    from . import storage
    from .models import BackupDestination

    try:
        backup = Backup.objects.get(pk=backup_pk)
        destination = BackupDestination.objects.get(pk=destination_pk)
    except (Backup.DoesNotExist, BackupDestination.DoesNotExist):
        return

    if backup.status != Backup.Status.READY or not backup.path:
        return

    with transaction.atomic():
        backup.remote_status = Backup.RemoteStatus.UPLOADING
        backup.remote_destination = destination
        backup.remote_error = ""
        backup.save(update_fields=["remote_status", "remote_destination", "remote_error"])

    try:
        key = storage.upload(destination, Path(backup.path))
    except storage.StorageError as exc:
        logger.exception("upload failed")
        with transaction.atomic():
            backup.remote_status = Backup.RemoteStatus.FAILED
            backup.remote_error = str(exc)
            backup.save(update_fields=["remote_status", "remote_error"])
        close_old_connections()
        return

    with transaction.atomic():
        backup.remote_status = Backup.RemoteStatus.UPLOADED
        backup.remote_key = key
        backup.remote_error = ""
        backup.save(update_fields=["remote_status", "remote_key", "remote_error"])
    close_old_connections()


def sources_for_kind(kind: str) -> list[Path]:
    """Public: list of paths a backup of `kind` will compress."""
    data = Path(settings.MC_DATA_PATH)
    if kind == Backup.Kind.WORLD:
        # Vanilla, Paper and Forge all use these names by default.
        return [
            data / "world",
            data / "world_nether",
            data / "world_the_end",
        ]
    return [data]  # FULL


# Back-compat private alias kept for any internal caller.
_sources_for_kind = sources_for_kind


def directory_size(path: Path) -> int:
    """Total bytes of files under `path`, recursively. Skips unreadable nodes."""
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _run(pk: int) -> None:
    # Django opens a fresh DB connection per thread; close it cleanly when done.
    try:
        backup = Backup.objects.get(pk=pk)
    except Backup.DoesNotExist:
        return

    try:
        backup_root = Path(settings.BACKUP_PATH)
        backup_root.mkdir(parents=True, exist_ok=True)
        target = backup_root / f"{backup.name}.tar.gz"

        with transaction.atomic():
            backup.status = Backup.Status.RUNNING
            backup.path = str(target)
            backup.save(update_fields=["status", "path"])

        sources = [s for s in sources_for_kind(backup.kind) if s.exists()]
        if not sources:
            raise FileNotFoundError(f"No source paths exist for kind={backup.kind}")

        # tar.gz with a stable arcname so restore can find the right roots.
        with tarfile.open(target, "w:gz") as tar:
            for src in sources:
                tar.add(src, arcname=src.name)

        size = target.stat().st_size

        with transaction.atomic():
            backup.size_bytes = size
            backup.status = Backup.Status.READY
            backup.completed_at = datetime.now(timezone.utc)
            backup.error = ""
            backup.save(update_fields=["size_bytes", "status", "completed_at", "error"])

        logger.info("backup %s done (%s bytes)", backup.name, size)

        # Auto-upload to any destination flagged as such.
        from .models import BackupDestination
        for dest in BackupDestination.objects.filter(enabled=True, auto_upload=True):
            logger.info("queuing auto-upload of %s -> %s", backup.name, dest.name)
            trigger_upload(backup.pk, dest.pk)

    except Exception as exc:  # noqa: BLE001 — surface anything to the UI
        logger.exception("backup %s failed", backup.name)
        with transaction.atomic():
            backup.status = Backup.Status.FAILED
            backup.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:2000]}"
            backup.completed_at = datetime.now(timezone.utc)
            backup.save(update_fields=["status", "error", "completed_at"])
    finally:
        close_old_connections()
