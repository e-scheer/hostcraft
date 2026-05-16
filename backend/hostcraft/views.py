"""Top-level views."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views import View


class SpaView(View):
    """Serve the built Vue SPA (index.html) in prod.

    In dev the SPA runs on Vite (5173) and Django only serves /api/*, so this
    view is unused — but it returns a friendly 404 if hit.
    """

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        index = settings.SPA_INDEX
        if index.is_file():
            return HttpResponse(index.read_bytes(), content_type="text/html")
        return HttpResponseNotFound(
            "SPA has not been built. In development, open http://localhost:5173.",
            content_type="text/plain",
        )
