"""Minecraft server lifecycle endpoints.

All operations go through the docker-socket-proxy, which whitelists the calls
we're allowed to make. Any rejected call surfaces as a 403 from the proxy.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from docker.errors import APIError, DockerException, NotFound
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse
from rest_framework.permissions import AllowAny

from . import (
    docker_client,
    icon as icon_helpers,
    players as players_helpers,
    properties as properties_helpers,
    realtime as realtime_helpers,
    runtime as runtime_helpers,
)


def _serialize(s: docker_client.ContainerStatus) -> dict:
    return {
        "state": s.state,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "image": s.image,
        "health": s.health,
        "uptime_seconds": s.uptime_seconds,
        "error": s.error,
        "restart_count": s.restart_count,
        "crash_looping": s.crash_looping,
        "last_exit_code": s.last_exit_code,
    }


def _docker_error(exc: Exception) -> Response:
    if isinstance(exc, NotFound):
        return Response({"detail": _("Minecraft container not found.")}, status=404)
    if isinstance(exc, APIError):
        return Response({"detail": _("Docker API error: %(err)s") % {"err": exc}}, status=502)
    return Response({"detail": _("Cannot reach docker-proxy: %(err)s") % {"err": exc}}, status=503)


class StatusView(APIView):
    def get(self, _request: Request) -> Response:
        return Response(_serialize(docker_client.status()))


class RealtimeView(APIView):
    """GET /api/server/realtime/ — combined Docker stats + RCON snapshot."""

    def get(self, _request: Request) -> Response:
        return Response(realtime_helpers.snapshot())


class WatchdogView(APIView):
    """GET / PATCH /api/server/watchdog/ — auto-restart settings."""

    def get(self, _request: Request) -> Response:
        return Response(self._payload())

    def patch(self, request: Request) -> Response:
        from .models_watchdog import WatchdogConfig
        cfg = WatchdogConfig.current()

        if "enabled" in request.data:
            cfg.enabled = bool(request.data["enabled"])
        if "threshold_seconds" in request.data:
            try:
                v = int(request.data["threshold_seconds"])
                cfg.threshold_seconds = max(30, min(3600, v))
            except (TypeError, ValueError):
                pass
        if "max_restarts_per_hour" in request.data:
            try:
                v = int(request.data["max_restarts_per_hour"])
                cfg.max_restarts_per_hour = max(1, min(20, v))
            except (TypeError, ValueError):
                pass
        cfg.save()
        return Response(self._payload())

    def _payload(self) -> dict:
        from .models_watchdog import WatchdogConfig
        cfg = WatchdogConfig.current()
        return {
            "enabled": cfg.enabled,
            "threshold_seconds": cfg.threshold_seconds,
            "max_restarts_per_hour": cfg.max_restarts_per_hour,
            "last_restart_at": cfg.last_restart_at.isoformat() if cfg.last_restart_at else None,
            "total_restarts": cfg.total_restarts,
        }


class RealtimeHistoryView(APIView):
    """GET /api/server/realtime/history/?window=1h|6h|24h|7d

    Returns persisted PerfSamples so the chart survives navigation/reload.
    """

    WINDOWS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}

    def get(self, request: Request) -> Response:
        from datetime import timedelta
        from django.utils import timezone
        from .models import PerfSample

        window = request.query_params.get("window", "1h")
        seconds = self.WINDOWS.get(window, 3600)
        since = timezone.now() - timedelta(seconds=seconds)

        rows = list(PerfSample.objects.filter(t__gte=since).order_by("t"))
        # Decimate longer windows so the wire payload stays small.
        max_points = 360
        if len(rows) > max_points:
            step = len(rows) // max_points
            rows = rows[::step]

        return Response(
            {
                "window": window,
                "samples": [
                    {
                        "t": r.t.isoformat(),
                        "cpu_percent": r.cpu_percent,
                        "memory_used": r.memory_used,
                        "memory_limit": r.memory_limit,
                        "players_online": r.players_online,
                        "players_max": r.players_max,
                        "tps_1m": r.tps_1m,
                    }
                    for r in rows
                ],
            }
        )


class StartView(APIView):
    def post(self, _request: Request) -> Response:
        try:
            docker_client.start()
        except (NotFound, APIError, DockerException) as exc:
            return _docker_error(exc)
        return Response(_serialize(docker_client.status()))


class StopView(APIView):
    def post(self, request: Request) -> Response:
        timeout = int(request.data.get("timeout", 60) or 60)
        try:
            docker_client.stop(timeout=timeout)
        except (NotFound, APIError, DockerException) as exc:
            return _docker_error(exc)
        return Response(_serialize(docker_client.status()))


class RestartView(APIView):
    def post(self, request: Request) -> Response:
        timeout = int(request.data.get("timeout", 60) or 60)
        try:
            docker_client.restart(timeout=timeout)
        except (NotFound, APIError, DockerException) as exc:
            return _docker_error(exc)
        return Response(_serialize(docker_client.status()))


class PropertiesView(APIView):
    """GET / PUT /api/server/properties/ — visual editor for server.properties."""

    def get(self, _request: Request) -> Response:
        return Response(self._payload())

    def put(self, request: Request) -> Response:
        new_values = request.data.get("values")
        if not isinstance(new_values, dict):
            return Response(
                {"detail": _("Invalid payload — expected an object under `values`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path = properties_helpers.properties_path()
        existing = properties_helpers.parse(path.read_text("utf-8")) if path.exists() else {}

        for key, value in new_values.items():
            coerced = properties_helpers.coerce(key, value)
            if coerced is not None:
                existing[key] = coerced

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(properties_helpers.serialize(existing), encoding="utf-8")
        return Response(self._payload())

    @staticmethod
    def _payload() -> dict:
        path = properties_helpers.properties_path()
        raw = properties_helpers.parse(path.read_text("utf-8")) if path.exists() else {}
        unknown = sorted(k for k in raw if k not in properties_helpers.SCHEMA)
        return {
            "values": properties_helpers.deserialize_typed(raw),
            "schema": properties_helpers.SCHEMA,
            "sections": properties_helpers.SECTIONS,
            "unknown_keys": unknown,
        }


# ---------------------------------------------------------------------------
# Whitelist + Ops
# ---------------------------------------------------------------------------


class WhitelistView(APIView):
    def get(self, _request: Request) -> Response:
        return Response({"entries": players_helpers.read_whitelist()})

    def post(self, request: Request) -> Response:
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"detail": _("Player name is required.")}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            entry = players_helpers.add_whitelist(name)
        except players_helpers.PlayerLookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"entry": entry, "entries": players_helpers.read_whitelist()})

    def delete(self, request: Request) -> Response:
        uuid = request.query_params.get("uuid", "").strip()
        if not uuid:
            return Response(
                {"detail": _("Missing uuid query parameter.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not players_helpers.remove_whitelist(uuid):
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response({"entries": players_helpers.read_whitelist()})


class OpsView(APIView):
    def get(self, _request: Request) -> Response:
        return Response({"entries": players_helpers.read_ops()})

    def post(self, request: Request) -> Response:
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"detail": _("Player name is required.")}, status=status.HTTP_400_BAD_REQUEST
            )
        level = request.data.get("level", players_helpers.DEFAULT_OP_LEVEL)
        bypass = bool(request.data.get("bypassesPlayerLimit", False))
        try:
            entry = players_helpers.add_op(name, level=level, bypasses_player_limit=bypass)
        except players_helpers.PlayerLookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"entry": entry, "entries": players_helpers.read_ops()})

    def patch(self, request: Request) -> Response:
        uuid = request.query_params.get("uuid", "").strip()
        if not uuid:
            return Response(
                {"detail": _("Missing uuid query parameter.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        level = request.data.get("level")
        bypass = request.data.get("bypassesPlayerLimit")
        entry = players_helpers.update_op(
            uuid,
            level=level if level is not None else None,
            bypasses_player_limit=bypass if bypass is not None else None,
        )
        if entry is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response({"entry": entry, "entries": players_helpers.read_ops()})

    def delete(self, request: Request) -> Response:
        uuid = request.query_params.get("uuid", "").strip()
        if not uuid:
            return Response(
                {"detail": _("Missing uuid query parameter.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not players_helpers.remove_op(uuid):
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response({"entries": players_helpers.read_ops()})


# ---------------------------------------------------------------------------
# Runtime tuning (Java memory, Aikar flags, JVM args)
# ---------------------------------------------------------------------------


def _serialize_runtime(s: runtime_helpers.RuntimeSnapshot) -> dict:
    return {
        "image": s.image,
        "image_tag": runtime_helpers.parse_image_tag(s.image),
        "state": s.state,
        "error": s.error,
        # Only expose the editable subset to the client. Everything else stays
        # internal — the user shouldn't see RCON_PASSWORD or unrelated env.
        "values": {key: s.env.get(key, "") for key in runtime_helpers.EDITABLE_ENV_KEYS},
        "editable_keys": sorted(runtime_helpers.EDITABLE_ENV_KEYS),
        "risky_keys": sorted(runtime_helpers.RISKY_KEYS),
    }


class RuntimeOptionsView(APIView):
    """GET /api/server/runtime/options/ — UI dropdowns for type & version."""

    def get(self, _request: Request) -> Response:
        snap = runtime_helpers.snapshot()
        # Resolve the configured MC version so the UI can pre-compute the
        # compatibility hint (min Java X required for current MC) without a
        # second round-trip.
        raw_mc = snap.env.get("VERSION", "")
        try:
            from mods.mojang import resolve as _resolve_mc
            resolved_mc = _resolve_mc(raw_mc) or raw_mc
        except Exception:  # noqa: BLE001
            resolved_mc = raw_mc
        return Response({
            "types": runtime_helpers.SUPPORTED_TYPES,
            "version_presets": runtime_helpers.VERSION_PRESETS,
            "java_tags": runtime_helpers.JAVA_TAGS,
            "current_image_tag": runtime_helpers.parse_image_tag(snap.image),
            "min_java_for_current_mc":
                runtime_helpers.min_java_for_mc(resolved_mc) if resolved_mc else None,
            "recommended_java_for_current_mc":
                runtime_helpers.recommended_java_for_mc(resolved_mc) if resolved_mc else None,
            "resolved_mc_version": resolved_mc,
        })


class RuntimeView(APIView):
    """GET / PUT /api/server/runtime/ — read & apply Java tuning overrides."""

    def get(self, _request: Request) -> Response:
        return Response(_serialize_runtime(runtime_helpers.snapshot()))

    def put(self, request: Request) -> Response:
        overrides = request.data.get("values")
        if not isinstance(overrides, dict):
            return Response(
                {"detail": _("Invalid payload — expected an object under `values`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_tag = request.data.get("image_tag")
        if image_tag is not None and not isinstance(image_tag, str):
            return Response(
                {"detail": _("`image_tag` must be a string.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        engine_reset = bool(request.data.get("engine_reset"))
        try:
            new_snap = runtime_helpers.apply_overrides(
                overrides, image_tag=image_tag, engine_reset=engine_reset,
            )
        except runtime_helpers.RuntimeError_ as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except NotFound:
            return Response(
                {"detail": _("Minecraft container not found.")},
                status=status.HTTP_404_NOT_FOUND,
            )
        except APIError as exc:
            return Response(
                {"detail": _("Docker API error: %(err)s") % {"err": exc}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except DockerException as exc:
            return Response(
                {"detail": _("Cannot reach docker-proxy: %(err)s") % {"err": exc}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(_serialize_runtime(new_snap))


# ---------------------------------------------------------------------------
# Server icon
# ---------------------------------------------------------------------------


def _icon_payload() -> dict:
    state = icon_helpers.current_state()
    return {
        "current": state,
        "presets": icon_helpers.list_presets(),
        "max_upload_bytes": icon_helpers.MAX_UPLOAD_BYTES,
        "size": icon_helpers.SIZE,
    }


class IconView(APIView):
    """GET / DELETE /api/server/icon/ — current icon state, reset."""

    def get(self, _request: Request) -> Response:
        return Response(_icon_payload())

    def delete(self, _request: Request) -> Response:
        icon_helpers.remove()
        return Response(_icon_payload())


class IconUploadView(APIView):
    """PUT /api/server/icon/upload/ — multipart custom upload."""

    def put(self, request: Request) -> Response:
        f = request.FILES.get("file")
        if f is None:
            return Response(
                {"detail": _("No file provided. Use multipart field `file`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            icon_helpers.apply_upload(f.read(), declared_content_type=f.content_type)
        except icon_helpers.IconError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_icon_payload())


class IconPresetView(APIView):
    """POST /api/server/icon/preset/ {id} — apply a preset."""

    def post(self, request: Request) -> Response:
        preset_id = (request.data.get("id") or "").strip()
        if not preset_id:
            return Response(
                {"detail": _("Missing preset `id`.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not icon_helpers.apply_preset(preset_id):
            return Response(
                {"detail": _("Unknown preset.")},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_icon_payload())


class IconRawView(APIView):
    """GET /api/server/icon/raw/ — serve the current PNG bytes.

    Public so the icon can be displayed in plain ``<img>`` tags (no Bearer
    token). The icon is by nature a public-facing artifact (Minecraft itself
    surfaces it on the multiplayer list).
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, _request: Request) -> HttpResponse:
        data = icon_helpers.read_current()
        if data is None:
            return HttpResponse(status=404)
        resp = HttpResponse(data, content_type="image/png")
        resp["Cache-Control"] = "no-cache"
        return resp


class IconPresetRawView(APIView):
    """GET /api/server/icon/presets/<id>/raw/ — serve a preset's PNG bytes.

    Public — these are generated gradients, no user data.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, _request: Request, preset_id: str) -> HttpResponse:
        data = icon_helpers.get_preset_bytes(preset_id)
        if data is None:
            return HttpResponse(status=404)
        resp = HttpResponse(data, content_type="image/png")
        resp["Cache-Control"] = "public, max-age=86400"
        return resp
