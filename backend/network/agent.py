"""Managed Playit agent — sidecar container we run for the user.

The user supplies their Playit secret (issued by playit.gg when they create
a tunnel for their Minecraft server). We launch ``ghcr.io/playit-cloud/playit-agent``
on the same Docker network as the MC container so it can dial ``minecraft:25565``
internally — no port mapping needed, the agent itself only outbounds.

Lifecycle:
- ``start(secret)`` — pull (if needed), create + start the container
- ``stop()`` — stop + remove
- ``status()`` — running / stopped / starting / absent
- ``logs(tail)`` — last ``tail`` log lines, useful so the UI can surface
  the claim URL when the user runs an unclaimed agent

The container name lives in :func:`agent_container_name`. Auto-restart
policy is ``unless-stopped`` so the agent survives a host reboot.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import docker
from docker.errors import APIError, DockerException, NotFound
from django.conf import settings

logger = logging.getLogger(__name__)

AGENT_IMAGE = "ghcr.io/playit-cloud/playit-agent:0.15"

# Playit hands out hostnames on a few free/paid TLDs. They can carry one
# or more subdomain levels (``foo.joinmc.link``, ``foo.bar.joinmc.link``).
# We accept both shapes so log scraping doesn't truncate a real hostname
# down to its parent zone.
_HOST_RE = re.compile(
    r"\b((?:[a-z0-9][a-z0-9-]*\.)+(?:joinmc\.link|playit\.gg))\b",
    re.IGNORECASE,
)


def agent_container_name() -> str:
    # Sit on the same naming pattern as the MC container so prod & dev
    # can override via env, and so logs / docker ps stay readable.
    return f"{settings.MC_CONTAINER_NAME}-playit"


def _client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.DOCKER_HOST, timeout=15)


@dataclass(frozen=True)
class AgentStatus:
    state: str           # 'absent' | 'created' | 'running' | 'restarting' | 'exited' | 'error'
    image: str = ""
    started_at: str | None = None
    error: str | None = None


def status() -> AgentStatus:
    try:
        c = _client().containers.get(agent_container_name())
    except NotFound:
        return AgentStatus(state="absent")
    except DockerException as exc:
        logger.warning("docker-proxy unreachable: %s", exc)
        return AgentStatus(state="error", error=str(exc))

    state = (c.attrs.get("State") or {}).get("Status") or "unknown"
    image = (c.attrs.get("Config") or {}).get("Image", "") or ""
    started_at = (c.attrs.get("State") or {}).get("StartedAt")
    return AgentStatus(state=state, image=image, started_at=started_at)


def _mc_running() -> bool:
    """True when the MC container exists and is currently up."""
    try:
        c = _client().containers.get(settings.MC_CONTAINER_NAME)
    except (NotFound, DockerException):
        return False
    return (c.attrs.get("State") or {}).get("Status") == "running"


# Playit's "Local IP" is fixed to 127.0.0.1: the agent shares the MC
# container's network namespace, so localhost from the agent's POV *is*
# the Minecraft server.
PLAYIT_LOCAL_TARGET = "127.0.0.1"


def start(secret: str) -> AgentStatus:
    """Idempotent — replaces any existing agent container.

    The agent runs in the **same network namespace** as the MC container
    (``network_mode=container:<MC>``). This means the agent's
    ``localhost`` is literally the MC server's network stack, so the user
    pastes ``127.0.0.1`` into playit.gg's "Local IP" field and it never
    has to change — no custom subnet, no static IP plumbing, no DNS
    pinning. Portable across any Docker host (Linux, Docker Desktop,
    Tailscale-laden machines, corporate networks).

    Caveat: the agent inherits MC's network namespace, so if MC isn't
    running yet we refuse to start. Callers must boot MC first. We also
    bounce the agent automatically whenever MC is stopped or recreated
    (see :func:`restart_if_was_running`).
    """
    client = _client()
    name = agent_container_name()

    if not _mc_running():
        return AgentStatus(
            state="error",
            error="Start the Minecraft server first — the Playit agent "
                  "shares its network namespace.",
        )

    # Pull the image. Cheap when already present (HEAD-style check).
    try:
        client.images.pull(AGENT_IMAGE)
    except (APIError, DockerException) as exc:
        # Pull may fail behind a strict proxy — try to start with whatever's
        # local and bubble up the error if there's nothing.
        logger.info("playit agent pull skipped: %s", exc)

    _force_remove(name)

    try:
        client.containers.run(
            AGENT_IMAGE,
            detach=True,
            name=name,
            environment={"SECRET_KEY": secret},
            restart_policy={"Name": "unless-stopped"},
            # The magic line — share MC's net namespace so 127.0.0.1
            # routes to its TCP/UDP services.
            network_mode=f"container:{settings.MC_CONTAINER_NAME}",
            labels={"hostcraft.role": "playit-agent"},
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
        )
    except (APIError, DockerException) as exc:
        return AgentStatus(state="error", error=str(exc))
    return status()


def _force_remove(name: str) -> None:
    try:
        old = _client().containers.get(name)
    except NotFound:
        return
    except DockerException:
        return
    try:
        old.stop(timeout=5)
    except APIError:
        pass
    try:
        old.remove(force=True)
    except APIError:
        pass


def restart_if_was_running() -> bool:
    """Bounce the agent after an MC stop/restart/recreate.

    Called from ``docker_client`` lifecycle helpers and from
    ``runtime.apply_overrides``: when the MC container goes away, the
    agent's shared network namespace evaporates with it. We re-spawn the
    agent with the stored secret so the tunnel comes back up automatically.

    Returns True when we actually started a new agent, False otherwise.
    """
    try:
        existed = _client().containers.get(agent_container_name())
    except (NotFound, DockerException):
        return False
    # Capture the secret from DB — we never read it back from the agent's
    # env, which could leak via docker inspect logs.
    try:
        from .models import NetworkProfile
        secret = NetworkProfile.current().playit_agent_key
    except Exception:  # noqa: BLE001
        secret = ""
    _force_remove(agent_container_name())
    if not secret:
        return False
    snap = start(secret)
    return snap.state in ("created", "running")


def stop() -> AgentStatus:
    try:
        c = _client().containers.get(agent_container_name())
    except NotFound:
        return AgentStatus(state="absent")
    except DockerException as exc:
        return AgentStatus(state="error", error=str(exc))
    try:
        c.stop(timeout=10)
        c.remove(force=True)
    except APIError as exc:
        return AgentStatus(state="error", error=str(exc))
    return AgentStatus(state="absent")


def logs(tail: int = 200) -> str:
    try:
        c = _client().containers.get(agent_container_name())
    except (NotFound, DockerException):
        return ""
    try:
        raw = c.logs(stdout=True, stderr=True, tail=tail, timestamps=False)
    except (APIError, DockerException) as exc:
        return f"<could not read logs: {exc}>"
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def detected_hostname(secret: str = "") -> str:
    """Best-effort discovery of the assigned tunnel hostname.

    Strategy, in priority order:

    1. **playit.gg API** — when a ``secret`` is provided, hit
       ``/agents/rundata`` and pick the Minecraft tunnel's hostname.
       Authoritative and works even before the sidecar has connected.

    2. **Container logs fallback** — scan the last few hundred lines of
       agent stdout for a ``*.joinmc.link`` / ``*.playit.gg`` match. Used
       when the API is unreachable or returns no tunnel yet.

    Returns ``""`` when nothing is known.
    """
    if secret:
        try:
            from . import playit_api
            host = playit_api.primary_hostname(secret)
            if host:
                return host
        except Exception:  # noqa: BLE001
            logger.exception("playit API lookup failed")

    text = logs(tail=500)
    if not text:
        return ""
    matches = _HOST_RE.findall(text)
    if not matches:
        return ""
    return matches[-1].lower()
