from __future__ import annotations

from datetime import datetime

from django.utils.dateparse import parse_datetime
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog


class AuditLogListView(APIView):
    """GET /api/audit/?limit=&since=&until=&status=&action=  — filterable.

    Query params (all optional):
      - limit:  number of entries (default 50, max 200)
      - since:  ISO-8601 datetime, inclusive lower bound on created_at
      - until:  ISO-8601 datetime, exclusive upper bound on created_at
      - status: 'success' | 'failed'
      - action: case-sensitive substring match on the dotted action name
    """

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def get(self, request: Request) -> Response:
        qs = AuditLog.objects.select_related("user").order_by("-created_at")

        since = _parse_dt(request.query_params.get("since"))
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        until = _parse_dt(request.query_params.get("until"))
        if until is not None:
            qs = qs.filter(created_at__lt=until)

        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter in {"success", "failed"}:
            qs = qs.filter(status=status_filter)

        action_filter = (request.query_params.get("action") or "").strip()
        if action_filter:
            qs = qs.filter(action__icontains=action_filter)

        try:
            limit = int(request.query_params.get("limit", self.DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT
        limit = max(1, min(self.MAX_LIMIT, limit))

        rows = qs[:limit]
        entries = [
            {
                "id": r.id,
                "user": r.user.username if r.user else None,
                "action": r.action,
                "method": r.method,
                "target": r.target,
                "status": r.status,
                "status_code": r.status_code,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
        return Response({"entries": entries, "count": len(entries), "limit": limit})


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    parsed = parse_datetime(raw)
    return parsed
