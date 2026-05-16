from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import service, storage
from .models import Backup, BackupDestination
from .serializers import BackupDestinationSerializer, BackupSerializer


_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _slugify_name(raw: str) -> str:
    base = _NAME_RE.sub("-", raw.strip()) or "backup"
    return base.strip("-")[:120] or "backup"


def _safe_backup_path(rel: str) -> Path:
    """Make sure the requested file is inside BACKUP_PATH (no traversal)."""
    root = Path(settings.BACKUP_PATH).resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionDenied(_("Backup path escapes the managed directory.")) from exc
    return candidate


class BackupListCreateView(APIView):
    def get(self, _request: Request) -> Response:
        backups = Backup.objects.all()
        return Response({"entries": BackupSerializer(backups, many=True).data})

    def post(self, request: Request) -> Response:
        kind = request.data.get("kind") or Backup.Kind.WORLD
        if kind not in dict(Backup.Kind.choices):
            return Response(
                {"detail": _("Unknown backup kind.")}, status=status.HTTP_400_BAD_REQUEST
            )

        raw_name = request.data.get("name")
        if raw_name:
            name = _slugify_name(str(raw_name))
        else:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"{kind}-{ts}"

        backup = Backup.objects.create(name=name, kind=kind, status=Backup.Status.PENDING)
        service.trigger(backup)
        return Response(BackupSerializer(backup).data, status=status.HTTP_201_CREATED)


class BackupDetailView(APIView):
    def get(self, _request: Request, pk: int) -> Response:
        try:
            backup = Backup.objects.get(pk=pk)
        except Backup.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response(BackupSerializer(backup).data)

    def delete(self, _request: Request, pk: int) -> Response:
        try:
            backup = Backup.objects.get(pk=pk)
        except Backup.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if backup.path:
            try:
                file_path = _safe_backup_path(Path(backup.path).name)
                if file_path.exists():
                    file_path.unlink()
            except (OSError, PermissionDenied):
                pass
        backup.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackupSizesView(APIView):
    """Estimate the on-disk size of each backup kind, before compression.

    The .tar.gz output is typically 30–60% smaller, but seeing the raw size
    helps the user decide between `world` and `full`.
    """

    def get(self, _request: Request) -> Response:
        return Response(
            {kind: _kind_size(kind) for kind, _ in Backup.Kind.choices}
        )


def _kind_size(kind: str) -> int:
    return sum(service.directory_size(p) for p in service.sources_for_kind(kind))


# ---------------------------------------------------------------------------
# Destinations (S3-compatible)
# ---------------------------------------------------------------------------


class DestinationListCreateView(APIView):
    def get(self, _request: Request) -> Response:
        return Response(
            {"entries": BackupDestinationSerializer(BackupDestination.objects.all(), many=True).data}
        )

    def post(self, request: Request) -> Response:
        ser = BackupDestinationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class DestinationDetailView(APIView):
    def get(self, _request: Request, pk: int) -> Response:
        dest = self._get(pk)
        if dest is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response(BackupDestinationSerializer(dest).data)

    def patch(self, request: Request, pk: int) -> Response:
        dest = self._get(pk)
        if dest is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        ser = BackupDestinationSerializer(dest, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, _request: Request, pk: int) -> Response:
        dest = self._get(pk)
        if dest is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        dest.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _get(pk: int) -> BackupDestination | None:
        try:
            return BackupDestination.objects.get(pk=pk)
        except BackupDestination.DoesNotExist:
            return None


class DestinationTestView(APIView):
    """POST /api/backups/destinations/<id>/test/ — list 1 object to probe creds."""

    def post(self, _request: Request, pk: int) -> Response:
        try:
            dest = BackupDestination.objects.get(pk=pk)
        except BackupDestination.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        try:
            storage.test_connection(dest)
        except storage.StorageError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_200_OK)
        return Response({"ok": True})


class BackupUploadView(APIView):
    """POST /api/backups/<id>/upload/?destination=<dest_id> — push to remote."""

    def post(self, request: Request, pk: int) -> Response:
        try:
            backup = Backup.objects.get(pk=pk)
        except Backup.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if backup.status != Backup.Status.READY:
            return Response(
                {"detail": _("Backup is not ready yet.")},
                status=status.HTTP_409_CONFLICT,
            )
        dest_id = request.query_params.get("destination") or request.data.get("destination")
        if not dest_id:
            return Response(
                {"detail": _("Missing destination id.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            destination = BackupDestination.objects.get(pk=int(dest_id), enabled=True)
        except (BackupDestination.DoesNotExist, ValueError):
            return Response(
                {"detail": _("Destination not found or disabled.")},
                status=status.HTTP_404_NOT_FOUND,
            )

        backup.remote_status = Backup.RemoteStatus.PENDING
        backup.remote_destination = destination
        backup.remote_error = ""
        backup.save(update_fields=["remote_status", "remote_destination", "remote_error"])
        service.trigger_upload(backup.pk, destination.pk)
        return Response(BackupSerializer(backup).data)


class BackupRestoreView(APIView):
    """POST /api/backups/<id>/restore/ — replace the world with this archive.

    Async: returns 202 immediately. Frontend polls the backups list to follow
    `restore_status` (running → done | failed). A safety auto-backup is
    created first; if it fails, the restore is aborted.
    """

    def post(self, _request: Request, pk: int) -> Response:
        try:
            backup = Backup.objects.get(pk=pk)
        except Backup.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if backup.status != Backup.Status.READY:
            return Response(
                {"detail": _("Backup is not ready yet.")},
                status=status.HTTP_409_CONFLICT,
            )
        if backup.restore_status == Backup.RestoreStatus.RUNNING:
            return Response(
                {"detail": _("A restore is already running.")},
                status=status.HTTP_409_CONFLICT,
            )

        backup.restore_status = Backup.RestoreStatus.RUNNING
        backup.restore_error = ""
        backup.save(update_fields=["restore_status", "restore_error"])
        service.trigger_restore(backup.pk)
        return Response(BackupSerializer(backup).data, status=status.HTTP_202_ACCEPTED)


class BackupDownloadView(APIView):
    def get(self, _request: Request, pk: int):
        try:
            backup = Backup.objects.get(pk=pk)
        except Backup.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if backup.status != Backup.Status.READY or not backup.path:
            return Response(
                {"detail": _("Backup is not ready yet.")},
                status=status.HTTP_409_CONFLICT,
            )
        file_path = _safe_backup_path(Path(backup.path).name)
        if not file_path.is_file():
            return Response(
                {"detail": _("Backup file missing on disk.")},
                status=status.HTTP_404_NOT_FOUND,
            )
        return FileResponse(file_path.open("rb"), as_attachment=True, filename=file_path.name)
