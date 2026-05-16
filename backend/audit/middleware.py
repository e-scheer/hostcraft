"""Auto-log every mutation under /api/* to the AuditLog table.

Drives the Dashboard's "Recent activity" feed. We don't audit GETs — they're
not actions. We don't audit /api/auth/login/ either — failed logins should
land in security logs (separate concern), and successful ones aren't actions
on the panel itself.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from .models import AuditLog

logger = logging.getLogger(__name__)


# Paths whose mutations we deliberately skip — auth and refresh aren't user
# actions in the AuditLog sense.
SKIP_PATH_PREFIXES = (
    "/api/auth/login/",
    "/api/auth/refresh/",
)


class AuditMiddleware(MiddlewareMixin):
    """Records POST/PUT/PATCH/DELETE on /api/* paths after the response is built."""

    def process_request(self, request: HttpRequest) -> None:
        # Stash a start time so we can compute duration in process_response.
        request._audit_started_at = time.monotonic()  # type: ignore[attr-defined]

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        try:
            self._maybe_record(request, response)
        except Exception:  # noqa: BLE001 — auditing must never break the response
            logger.exception("audit middleware failed")
        return response

    def _maybe_record(self, request: HttpRequest, response: HttpResponse) -> None:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        path = request.path or ""
        if not path.startswith("/api/"):
            return
        if any(path.startswith(p) for p in SKIP_PATH_PREFIXES):
            return

        user = getattr(request, "user", None)
        if user is not None and not user.is_authenticated:
            user = None

        action = _derive_action(path)
        status_code = response.status_code
        status = AuditLog.Status.SUCCESS if 200 <= status_code < 400 else AuditLog.Status.FAILED

        started: float | None = getattr(request, "_audit_started_at", None)
        duration_ms = int((time.monotonic() - started) * 1000) if started else None

        # Best-effort target hint — query string `path=` is widely used in our
        # files/backups APIs, otherwise the URL itself.
        target = (
            request.GET.get("path")
            or request.GET.get("uuid")
            or request.GET.get("destination")
            or path
        )

        AuditLog.objects.create(
            user=user,
            action=action,
            method=request.method,
            target=str(target)[:255],
            payload={},
            status_code=status_code,
            status=status,
            duration_ms=duration_ms,
        )


def _derive_action(path: str) -> str:
    """Turn `/api/server/start/` into `server.start`, drop numeric ids."""
    parts = [p for p in path.split("/") if p and p != "api"]
    parts = [p for p in parts if not p.isdigit()]
    return ".".join(parts).strip(".")[:64] or "unknown"
