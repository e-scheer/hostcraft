from __future__ import annotations

from django.utils.translation import gettext as _
from docker.errors import APIError, DockerException, NotFound
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import agent as playit_agent
from . import dns_preview, public_ip, service
from .models import Allocation, NetworkProfile
from .serializers import AllocationSerializer, NetworkProfileSerializer


class ProfileView(APIView):
    """GET / PATCH /api/network/  — singleton config."""

    def get(self, _request: Request) -> Response:
        return Response(self._payload())

    def patch(self, request: Request) -> Response:
        profile = NetworkProfile.current()
        ser = NetworkProfileSerializer(profile, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(self._payload())

    def _payload(self) -> dict:
        profile = NetworkProfile.current()
        allocations = list(Allocation.objects.all())
        # Read primary MC port from server.properties as best-effort. Falls
        # back to 25565 if anything goes wrong.
        primary_port = _read_primary_port()
        return {
            "profile": NetworkProfileSerializer(profile).data,
            "public_ip": public_ip.detect(),
            "primary_port": primary_port,
            "allocations": AllocationSerializer(allocations, many=True).data,
            "dns_records": dns_preview.build_records(profile, allocations, primary_port),
        }


class AllocationListCreateView(APIView):
    def get(self, _request: Request) -> Response:
        return Response({"entries": AllocationSerializer(Allocation.objects.all(), many=True).data})

    def post(self, request: Request) -> Response:
        ser = AllocationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        try:
            service.sync_to_container()
        except (NotFound, APIError, DockerException) as exc:
            # The DB row is created. Surface the docker error so the user
            # knows the container wasn't recreated yet.
            return Response(
                {"entry": ser.data, "warning": str(exc)},
                status=status.HTTP_207_MULTI_STATUS,
            )
        return Response(ser.data, status=status.HTTP_201_CREATED)


class AllocationDetailView(APIView):
    def patch(self, request: Request, pk: int) -> Response:
        alloc = self._get(pk)
        if alloc is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        ser = AllocationSerializer(alloc, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        try:
            service.sync_to_container()
        except (NotFound, APIError, DockerException) as exc:
            return Response(
                {"entry": ser.data, "warning": str(exc)},
                status=status.HTTP_207_MULTI_STATUS,
            )
        return Response(ser.data)

    def delete(self, _request: Request, pk: int) -> Response:
        alloc = self._get(pk)
        if alloc is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        alloc.delete()
        try:
            service.sync_to_container()
        except (NotFound, APIError, DockerException) as exc:
            return Response({"warning": str(exc)}, status=status.HTTP_207_MULTI_STATUS)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _get(pk: int) -> Allocation | None:
        try:
            return Allocation.objects.get(pk=pk)
        except Allocation.DoesNotExist:
            return None


class RefreshPublicIpView(APIView):
    """POST /api/network/refresh-ip/ — bypass the 1h cache."""

    def post(self, _request: Request) -> Response:
        ip = public_ip.detect(force=True)
        return Response({"public_ip": ip})


class PlayitAgentView(APIView):
    """GET / POST / DELETE /api/network/playit/agent/

    GET    → status snapshot of the sidecar container
    POST   → start (or restart with new secret); body: {secret: str}
    DELETE → stop + remove the sidecar
    """

    def get(self, _request: Request) -> Response:
        return Response(_agent_payload())

    def post(self, request: Request) -> Response:
        secret = (request.data.get("secret") or "").strip()
        if not secret:
            # Allow restart-with-stored-secret when the body is empty.
            profile = NetworkProfile.current()
            secret = profile.playit_agent_key
            if not secret:
                return Response(
                    {"detail": _("Missing Playit secret. Paste it from your playit.gg dashboard.")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Persist the new secret so the user doesn't have to re-paste.
            profile = NetworkProfile.current()
            profile.playit_agent_key = secret
            profile.mode = NetworkProfile.Mode.PLAYIT_MANAGED
            profile.save(update_fields=["playit_agent_key", "mode", "updated_at"])

        snap = playit_agent.start(secret)
        if snap.error:
            return Response(
                {"detail": snap.error, **_agent_payload()},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(_agent_payload(), status=status.HTTP_201_CREATED)

    def delete(self, _request: Request) -> Response:
        playit_agent.stop()
        return Response(_agent_payload())


class PlayitAgentLogsView(APIView):
    """GET /api/network/playit/agent/logs/?tail=200 — last N log lines.

    Useful so the UI can surface the claim URL the agent prints on first
    boot, and to debug connect failures.
    """

    def get(self, request: Request) -> Response:
        try:
            tail = max(10, min(2000, int(request.query_params.get("tail", 200))))
        except (TypeError, ValueError):
            tail = 200
        return Response({"logs": playit_agent.logs(tail=tail)})


class PlayitAgentRefreshView(APIView):
    """POST /api/network/playit/agent/refresh/

    Forces a fresh round-trip to playit.gg's API, bypassing the cached
    tunnel list. Used after the user adds a tunnel on the playit.gg
    dashboard so the panel picks it up without waiting for the cache TTL.
    """

    def post(self, _request: Request) -> Response:
        profile = NetworkProfile.current()
        if not profile.playit_agent_key:
            return Response(
                {"detail": _("No Playit secret saved.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from . import playit_api
            playit_api.lookup_tunnels(profile.playit_agent_key, force=True)
        except Exception:  # noqa: BLE001
            pass
        return Response(_agent_payload())


def _agent_payload() -> dict:
    s = playit_agent.status()
    profile = NetworkProfile.current()
    detected = ""
    setup = "unknown"
    if profile.playit_agent_key:
        try:
            detected = playit_agent.detected_hostname(profile.playit_agent_key)
        except Exception:  # noqa: BLE001
            detected = ""
        try:
            from . import playit_api
            setup = playit_api.setup_state(profile.playit_agent_key)
        except Exception:  # noqa: BLE001
            setup = "unknown"
    return {
        "state": s.state,
        "image": s.image,
        "started_at": s.started_at,
        "error": s.error,
        "has_secret": bool(profile.playit_agent_key),
        "hostname": profile.playit_hostname,
        "detected_hostname": detected,
        # 'ready' (tunnel configured) | 'no_tunnel' (valid secret, nothing
        # set up on playit.gg yet) | 'unknown' (API unreachable / no secret).
        "playit_setup": setup,
        # The agent shares MC's network namespace (network_mode:container:),
        # so "Local IP" on playit.gg's tunnel page is *always* 127.0.0.1.
        # Stable across container recreations, host OS, Docker variants.
        "mc_container_ip": playit_agent.PLAYIT_LOCAL_TARGET,
    }


def _read_primary_port() -> int:
    try:
        from server.properties import properties_path, parse
        path = properties_path()
        if not path.exists():
            return 25565
        return int(parse(path.read_text("utf-8")).get("server-port", 25565))
    except Exception:  # noqa: BLE001
        return 25565
