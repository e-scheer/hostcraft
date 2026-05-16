"""World map endpoints."""

from __future__ import annotations

from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from mods.installer import InstallError
from mods.providers import ProviderError

from . import service


def _payload(s: service.WorldmapStatus) -> dict:
    return {
        "state": s.state,
        "filename": s.filename,
        "web_port": s.web_port,
        "target_kind": s.target_kind,
        "target_loader": s.target_loader,
    }


class WorldmapStatusView(APIView):
    """GET /api/worldmap/ — current state of the world-map mod."""

    def get(self, _request: Request) -> Response:
        return Response(_payload(service.status()))


class WorldmapInstallView(APIView):
    """POST /api/worldmap/install/ — install BlueMap."""

    def post(self, _request: Request) -> Response:
        try:
            result = service.install_bluemap()
        except (InstallError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(
            {"status": _payload(service.status()), "result": result},
            status=status.HTTP_201_CREATED,
        )
