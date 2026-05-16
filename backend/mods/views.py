"""Mods marketplace endpoints."""

from __future__ import annotations

from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import installer, inventory, manual_install, service
from .loader import configured_version_alias, current_mc_version, detect
from .models import InstalledMod
from .providers import ProviderError


def _target_payload() -> dict:
    t = detect()
    mc = current_mc_version()
    alias = configured_version_alias()
    return {
        "kind": t.kind,
        "folder": t.folder,
        "loaders": list(t.loaders),
        "loader_label": t.loader_label,
        "mc_version": mc,
        "mc_version_alias": alias if alias and alias.upper() != mc.upper() else "",
    }


class TargetView(APIView):
    """GET /api/mods/target/ — what kind of mod/plugin runs here right now."""

    def get(self, _request: Request) -> Response:
        return Response(_target_payload())


class SearchView(APIView):
    """GET /api/mods/search/?q=…&limit=24&offset=0"""

    def get(self, request: Request) -> Response:
        q = request.query_params.get("q", "").strip()
        try:
            limit = max(1, min(50, int(request.query_params.get("limit", 24))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            return Response({"detail": "Invalid limit/offset."},
                            status=status.HTTP_400_BAD_REQUEST)
        # When the UI passes strict_version=0 we drop the MC-version filter
        # so the user can browse projects whose authors haven't shipped a
        # release for the current version yet.
        strict_version = request.query_params.get("strict_version", "1") != "0"

        try:
            payload = service.unified_search(
                q, limit=limit, offset=offset, strict_version=strict_version,
            )
        except ProviderError as exc:
            return Response({"detail": str(exc)},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response(payload)


class VersionsView(APIView):
    """GET /api/mods/versions/?provider=modrinth&project_id=…"""

    def get(self, request: Request) -> Response:
        provider = request.query_params.get("provider", "")
        project_id = request.query_params.get("project_id", "")
        if not provider or not project_id:
            return Response(
                {"detail": _("Missing provider or project_id.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            versions = service.fetch_versions(provider, project_id)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"versions": versions})


class InstalledView(APIView):
    """GET /api/mods/installed/ — what's tracked + untracked jars on disk."""

    def get(self, _request: Request) -> Response:
        return Response({
            "tracked": inventory.list_tracked(),
            "untracked": inventory.list_untracked(),
            "target": _target_payload(),
        })


class InstallView(APIView):
    """POST /api/mods/install/ — install a project at a specific (or latest) version."""

    def post(self, request: Request) -> Response:
        provider = (request.data.get("provider") or "").strip()
        project_id = (request.data.get("project_id") or "").strip()
        version_id = request.data.get("version_id") or None
        if not provider or not project_id:
            return Response(
                {"detail": _("Missing provider or project_id.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            res = installer.install(provider, project_id, version_id)
        except installer.InstallError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({
            "id": res.record.id,
            "filename": res.record.filename,
            "verified": res.verified,
            "bytes_written": res.bytes_written,
        }, status=status.HTTP_201_CREATED)


class UninstallView(APIView):
    """DELETE /api/mods/<id>/"""

    def delete(self, _request: Request, pk: int) -> Response:
        try:
            removed = installer.uninstall(pk)
        except InstalledMod.DoesNotExist:
            return Response({"detail": _("Not found.")},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({"removed": removed}, status=status.HTTP_200_OK)


class ManualInspectView(APIView):
    """POST /api/mods/upload/inspect/ — peek inside a file before installing.

    Returns detected metadata + a compatibility verdict against the
    running server so the UI can show "this is Forge 1.20.1, your server
    is Forge 1.20.1, ✓ compatible".
    """

    def post(self, request: Request) -> Response:
        f = request.FILES.get("file")
        if f is None:
            return Response(
                {"detail": _("No file provided. Use multipart field `file`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if f.size > manual_install.MAX_UPLOAD_BYTES:
            return Response(
                {"detail": _("File too large (max %(n)d MB).") % {
                    "n": manual_install.MAX_UPLOAD_BYTES // 1024 // 1024
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )
        meta = manual_install.inspect(f, f.name)
        t = detect()
        verdict = manual_install.compat_verdict(
            meta, t.loaders or [], current_mc_version(),
        )
        return Response({
            "meta": meta.to_dict(),
            "verdict": verdict,
            "filename": f.name,
            "size": f.size,
            "target": {
                "kind": t.kind,
                "loaders": list(t.loaders),
                "loader_label": t.loader_label,
                "mc_version": current_mc_version(),
            },
        })


class ManualInstallView(APIView):
    """POST /api/mods/upload/ — commit the uploaded file to disk.

    Optional ``force_kind`` form field lets the user override what we
    detected (handy when the archive has no recognisable metadata).
    """

    def post(self, request: Request) -> Response:
        f = request.FILES.get("file")
        if f is None:
            return Response(
                {"detail": _("No file provided. Use multipart field `file`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        force_kind = (request.data.get("force_kind") or "").strip() or None
        if force_kind and force_kind not in {"mod", "plugin"}:
            return Response(
                {"detail": _("force_kind must be 'mod' or 'plugin'.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = manual_install.install(
                f, f.name, f.size, force_kind=force_kind,
            )
        except manual_install.ManualInstallError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)
