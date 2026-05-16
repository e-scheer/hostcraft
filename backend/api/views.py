"""Top-level API endpoints (health, version)."""

from __future__ import annotations

from datetime import datetime, timezone

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, _request: Request) -> Response:
        return Response({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


class VersionView(APIView):
    permission_classes = [AllowAny]

    def get(self, _request: Request) -> Response:
        return Response({"name": "hostcraft", "version": "0.0.0-dev"})
