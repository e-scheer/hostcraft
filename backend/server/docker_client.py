"""Thin wrapper around the Docker SDK, pointed at the docker-socket-proxy.

We never talk to the raw socket — the proxy enforces a whitelist. Any call
outside that whitelist returns 403 from the proxy and we surface it as an
explicit error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import docker
from docker.errors import APIError, DockerException, NotFound
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContainerStatus:
    state: str  # "running" | "exited" | "created" | "restarting" | "paused" | "absent" | "error"
    started_at: Optional[datetime] = None
    image: str = ""
    health: Optional[str] = None
    error: Optional[str] = None
    restart_count: int = 0
    crash_looping: bool = False
    last_exit_code: Optional[int] = None

    @property
    def uptime_seconds(self) -> Optional[int]:
        if self.state != "running" or self.started_at is None:
            return None
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds())


def _client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.DOCKER_HOST, timeout=10)


def _get_container():
    """Return the managed container, or None if absent.

    Raises DockerException on connectivity / proxy errors.
    """
    return _client().containers.get(settings.MC_CONTAINER_NAME)


def status() -> ContainerStatus:
    """Snapshot of the managed Minecraft container."""
    try:
        c = _get_container()
    except NotFound:
        return ContainerStatus(state="absent")
    except DockerException as exc:
        logger.warning("Docker proxy unreachable: %s", exc)
        return ContainerStatus(state="error", error=str(exc))

    state = c.attrs.get("State", {}) or {}
    raw_state = state.get("Status") or "unknown"
    started_at = _parse_iso(state.get("StartedAt"))

    # Read the image straight off the container attrs we already fetched.
    # Going through ``c.image`` lazy-loads via ``GET /images/<id>/json``,
    # which the docker-socket-proxy refuses (IMAGES=0) — surfacing as a
    # 403 burst on every status poll.
    image = (c.attrs.get("Config") or {}).get("Image", "") or ""

    health = None
    if isinstance(state.get("Health"), dict):
        health = state["Health"].get("Status")

    restart_count = int(c.attrs.get("RestartCount") or 0)
    last_exit_code = state.get("ExitCode")
    if not isinstance(last_exit_code, int):
        last_exit_code = None

    # Crash-loop heuristic: Docker auto-restart bounced the container at
    # least 3 times AND the current incarnation is either freshly started
    # or already exited. RestartCount keeps incrementing until the manual
    # ``docker stop`` resets it, so we also require a recent boot to not
    # falsely flag servers that survived a single rough patch days ago.
    crash_looping = False
    if restart_count >= 3:
        if raw_state == "restarting":
            crash_looping = True
        elif raw_state == "running" and started_at is not None:
            uptime = (datetime.now(timezone.utc) - started_at).total_seconds()
            if uptime < 60:
                crash_looping = True
        elif raw_state == "exited" and last_exit_code not in (0, None):
            crash_looping = True

    return ContainerStatus(
        state=raw_state,
        started_at=started_at,
        image=image,
        health=health,
        restart_count=restart_count,
        crash_looping=crash_looping,
        last_exit_code=last_exit_code,
    )


def start() -> None:
    c = _get_container()
    c.start()
    # The Playit sidecar shares MC's network namespace — when MC comes
    # back up we re-spawn the agent so the tunnel reattaches to the new
    # netns. No-op if no secret is stored.
    try:
        from network import agent
        agent.restart_if_was_running()
    except Exception:  # noqa: BLE001
        logger.exception("could not respawn playit agent after MC start")


def stop(timeout: int = 60) -> None:
    # Drop the cached RCON socket and the playit sidecar — both depend on
    # the MC container being alive.
    from . import rcon
    rcon.reset()
    try:
        from network import agent
        agent.stop()
    except Exception:  # noqa: BLE001
        logger.exception("could not stop playit agent before MC stop")
    c = _get_container()
    c.stop(timeout=timeout)


def restart(timeout: int = 60) -> None:
    from . import rcon
    rcon.reset()
    c = _get_container()
    c.restart(timeout=timeout)
    try:
        from network import agent
        agent.restart_if_was_running()
    except Exception:  # noqa: BLE001
        logger.exception("could not respawn playit agent after MC restart")


def stats() -> dict:
    """One-shot Docker stats: CPU%, memory used/limit. Returns None values if
    the container isn't running or the proxy refuses /stats."""
    out: dict = {
        "cpu_percent": None,
        "memory_used": None,
        "memory_limit": None,
    }
    try:
        c = _get_container()
        if c.status != "running":
            return out
        raw = c.stats(stream=False)
    except (NotFound, DockerException):
        return out

    cpu = raw.get("cpu_stats") or {}
    precpu = raw.get("precpu_stats") or {}
    cpu_total = (cpu.get("cpu_usage") or {}).get("total_usage", 0)
    pre_total = (precpu.get("cpu_usage") or {}).get("total_usage", 0)
    sys_total = cpu.get("system_cpu_usage") or 0
    pre_sys = precpu.get("system_cpu_usage") or 0
    online_cpus = (
        cpu.get("online_cpus")
        or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or [])
        or 1
    )
    cpu_delta = cpu_total - pre_total
    sys_delta = sys_total - pre_sys
    if sys_delta > 0 and cpu_delta > 0:
        out["cpu_percent"] = round((cpu_delta / sys_delta) * online_cpus * 100, 1)

    mem = raw.get("memory_stats") or {}
    if mem.get("usage") is not None:
        out["memory_used"] = int(mem["usage"])
    if mem.get("limit"):
        out["memory_limit"] = int(mem["limit"])
    return out


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw or raw.startswith("0001-"):
        return None
    try:
        # Docker emits e.g. "2026-05-03T16:30:00.123456789Z" — Python only handles
        # microseconds, so trim to 6 digits before parsing.
        if "." in raw:
            head, tail = raw.split(".", 1)
            tz = ""
            if tail.endswith("Z"):
                tail = tail[:-1]
                tz = "+00:00"
            elif "+" in tail:
                frac, offset = tail.split("+", 1)
                tail = frac
                tz = f"+{offset}"
            tail = tail[:6]  # microseconds
            raw = f"{head}.{tail}{tz}"
        else:
            raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
