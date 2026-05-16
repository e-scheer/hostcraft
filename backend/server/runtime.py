"""Runtime tuning of the managed Minecraft container.

Docker doesn't let you edit env vars on a running container — they're frozen at
creation time. So "applying" a runtime change here means: stop, remove,
recreate with the same specs *plus* the env overrides the user wants.

We preserve volumes, port bindings, networks, restart policy, labels and
security options from the existing container so the recreated one is
indistinguishable except for the env we touched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound
from django.conf import settings

logger = logging.getLogger(__name__)


# Env keys we accept from the UI. Anything else is filtered out before write.
EDITABLE_ENV_KEYS = {
    "TYPE",
    "VERSION",
    "MEMORY",
    "USE_AIKAR_FLAGS",
    "JVM_OPTS",
    "JVM_XX_OPTS",
}


# Subset of itzg's supported server types. Order matters — first ones come up
# higher in the UI. Free-form TYPE values stay accepted; this is just for the
# dropdown.
SUPPORTED_TYPES: list[dict[str, str]] = [
    {"value": "VANILLA", "label": "Vanilla", "loader": "vanilla"},
    {"value": "PAPER", "label": "Paper", "loader": "plugins"},
    {"value": "PURPUR", "label": "Purpur", "loader": "plugins"},
    {"value": "FOLIA", "label": "Folia", "loader": "plugins"},
    {"value": "SPIGOT", "label": "Spigot", "loader": "plugins"},
    {"value": "BUKKIT", "label": "Bukkit", "loader": "plugins"},
    {"value": "FABRIC", "label": "Fabric", "loader": "fabric"},
    {"value": "FORGE", "label": "Forge", "loader": "forge"},
    {"value": "NEOFORGE", "label": "NeoForge", "loader": "neoforge"},
    {"value": "QUILT", "label": "Quilt", "loader": "fabric"},
]


# itzg/minecraft-server publishes one image per Java major + a `latest` that
# auto-picks based on the requested MC version. We expose a curated subset.
IMAGE_REPO = "itzg/minecraft-server"
JAVA_TAGS: list[dict[str, Any]] = [
    {"tag": "latest", "label": "Auto (recommended)", "java": 0, "lts": True},
    {"tag": "java25", "label": "Java 25 (LTS)", "java": 25, "lts": True},
    {"tag": "java21", "label": "Java 21 (LTS)", "java": 21, "lts": True},
    {"tag": "java17", "label": "Java 17 (LTS)", "java": 17, "lts": True},
    {"tag": "java11", "label": "Java 11", "java": 11, "lts": False},
    {"tag": "java8",  "label": "Java 8",  "java": 8,  "lts": False},
]


def min_java_for_mc(mc_version: str) -> int:
    """Minimum Java major version required to run ``mc_version``.

    Falls back to 21 (current LTS) for unparseable input. ``LATEST``-style
    aliases should be resolved by the caller (see ``mods.mojang.resolve``)
    before calling this — we treat unknown shapes conservatively.
    """
    if not mc_version:
        return 21
    parts = mc_version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return 21

    # Mojang's date-based versioning (introduced 2026, e.g. 26.x).
    if major >= 26:
        return 25
    if major >= 22:
        return 21
    if major == 1:
        if minor >= 21:
            return 21
        if minor == 20 and patch >= 5:
            return 21
        if minor in (18, 19, 20):
            return 17
        if minor == 17:
            return 16
        return 8
    return 8


def recommended_java_for_mc(mc_version: str) -> int:
    """Java version we'd default to for ``mc_version``.

    This is the *target* a typical modpack of that era was built and
    QA'd against. Picking something newer is allowed but can break
    native libs that ship with mods (a frequent offender being spark's
    async-profiler on Java 25+).
    """
    if not mc_version:
        return 21
    parts = mc_version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return 21

    if major >= 26:
        return 25
    if major >= 22:
        return 21
    if major == 1:
        if minor >= 21:
            return 21
        if minor == 20 and patch >= 5:
            return 21
        # 1.18 - 1.20.4: Forge / Paper modpacks of this era were built
        # against Java 17. Java 21 also works but 17 is the safest pick.
        if minor in (18, 19, 20):
            return 17
        if minor == 17:
            return 17
        return 8
    return 8


def parse_image_tag(image: str) -> str:
    """Pull the tag out of ``itzg/minecraft-server:java21`` → ``java21``."""
    if ":" not in image:
        return "latest"
    return image.rsplit(":", 1)[-1]


# Curated common version pins. Free text accepted too — itzg resolves whatever
# Mojang/Paper/Fabric provides.
VERSION_PRESETS: list[str] = [
    "LATEST",
    "1.21.4",
    "1.21.1",
    "1.20.6",
    "1.20.4",
    "1.20.1",
    "1.19.4",
    "1.18.2",
    "1.16.5",
    "1.12.2",
    "1.8.9",
]


# Changing TYPE or VERSION can shred mods/plugins/world-format compatibility.
# Frontend uses this to surface a "safety backup" prompt before applying.
RISKY_KEYS = {"TYPE", "VERSION"}


@dataclass(frozen=True)
class RuntimeSnapshot:
    """The bits of the running container we surface in the UI."""
    image: str
    env: dict[str, str]
    state: str
    error: str | None = None


def _client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.DOCKER_HOST, timeout=15)


def snapshot() -> RuntimeSnapshot:
    try:
        c = _client().containers.get(settings.MC_CONTAINER_NAME)
    except NotFound:
        return RuntimeSnapshot(image="", env={}, state="absent")
    except DockerException as exc:
        logger.warning("Cannot reach docker-proxy: %s", exc)
        return RuntimeSnapshot(image="", env={}, state="error", error=str(exc))

    attrs = c.attrs or {}
    cfg = attrs.get("Config", {}) or {}
    env_list = cfg.get("Env") or []
    env: dict[str, str] = {}
    for entry in env_list:
        if "=" in entry:
            key, value = entry.split("=", 1)
            env[key] = value

    state = (attrs.get("State", {}) or {}).get("Status") or "unknown"
    image = cfg.get("Image") or ""
    return RuntimeSnapshot(image=image, env=env, state=state)


class RuntimeError_(Exception):
    """Validation error from apply_overrides (e.g. Java/MC incompat)."""


# (family, loader-folder) per supported TYPE. Same family → mods/plugins
# from the previous engine are still expected to work. Different family →
# the old loader's files won't load (different bytecode entrypoint) and
# can crash the new server when the loader folders overlap.
_FAMILY: dict[str, tuple[str, str | None]] = {
    "PAPER":    ("bukkit", "plugins"),
    "PURPUR":   ("bukkit", "plugins"),
    "FOLIA":    ("bukkit", "plugins"),
    "SPIGOT":   ("bukkit", "plugins"),
    "BUKKIT":   ("bukkit", "plugins"),
    "FORGE":    ("forge",  "mods"),
    "NEOFORGE": ("neoforge", "mods"),
    "FABRIC":   ("fabric", "mods"),
    "QUILT":    ("fabric", "mods"),     # quilt loads fabric mods
    "VANILLA":  ("vanilla", None),
}


def is_engine_swap(old_type: str, new_type: str) -> bool:
    """True when the two TYPEs sit in different loader families."""
    old = _FAMILY.get((old_type or "").upper())
    new = _FAMILY.get((new_type or "").upper())
    if old is None or new is None:
        return False
    return old[0] != new[0]


# Files we always preserve through an engine reset because the panel — or
# Mojang's EULA flow — manages them and they're shared across engines.
# Server.properties stays so the user's port / motd / whitelist toggle
# survive; the admin lists keep player permissions; the icon is just a
# server-icon.png the panel writes to MC_DATA_PATH.
_KEEP_AT_RESET = frozenset({
    "server.properties",
    "ops.json",
    "whitelist.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
    "eula.txt",
    "server-icon.png",
})


def _wipe_engine_reset() -> int:
    """Nuke the data dir clean except for the panel-managed identity files.

    Mods, plugins, configs, worlds, caches, libraries, logs, crash reports,
    engine-specific config trees (bukkit/, plugins/, mods/, defaultconfigs/,
    serverconfig/, …): all gone. itzg's image will re-bootstrap from a
    fresh state on the next boot.

    The user MUST have taken the full safety backup before this fires —
    that's the recovery path. The pre-apply dialog makes this clear.
    """
    import shutil
    from pathlib import Path
    from django.conf import settings as dj_settings

    base = Path(dj_settings.MC_DATA_PATH)
    if not base.is_dir():
        return 0

    removed = 0
    for entry in base.iterdir():
        if entry.name in _KEEP_AT_RESET:
            continue
        try:
            if entry.is_dir() or entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=False)
            else:
                entry.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("could not remove %s: %s", entry, exc)

    try:
        from mods.models import InstalledMod
        InstalledMod.objects.all().delete()
    except Exception:  # noqa: BLE001
        logger.exception("could not prune InstalledMod rows after engine reset")
    return removed


def apply_overrides(
    overrides: dict[str, Any] | None = None,
    extra_port_bindings: dict[str, list[dict[str, str]]] | None = None,
    image_tag: str | None = None,
    engine_reset: bool = False,
    force: bool = False,
) -> RuntimeSnapshot:
    """Recreate the MC container with `overrides` merged into its env.

    `extra_port_bindings` lets the network app add allocations on top of what
    the compose file already wires (Docker port-bindings dict shape, e.g.
    {"8100/tcp": [{"HostIp": "", "HostPort": "8100"}]}).

    `image_tag`: when set, swap the image to ``itzg/minecraft-server:<tag>``.
    Validated against ``JAVA_TAGS`` and rejected when the Java major is too
    old for the configured MC version (see :func:`min_java_for_mc`).

    `force=True` recreates even if no env change — useful when only port
    bindings change.

    Raises on Docker / proxy errors — callers translate to HTTP responses.
    Raises :class:`RuntimeError_` on validation failure.
    """
    overrides = overrides or {}
    extra_port_bindings = extra_port_bindings or {}

    cleaned: dict[str, str] = {}
    for key, value in overrides.items():
        if key not in EDITABLE_ENV_KEYS:
            continue
        if isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        elif value is None:
            continue
        else:
            cleaned[key] = str(value)

    if (
        not cleaned
        and not extra_port_bindings
        and image_tag is None
        and not engine_reset
        and not force
    ):
        return snapshot()

    # We're about to recreate the container — any cached RCON socket is dead.
    from . import rcon
    rcon.reset()

    client = _client()
    container = client.containers.get(settings.MC_CONTAINER_NAME)
    attrs = container.attrs or {}

    # ---- Replicate the existing container ---------------------------------
    cfg = attrs.get("Config", {}) or {}
    host_cfg = attrs.get("HostConfig", {}) or {}
    network_settings = attrs.get("NetworkSettings", {}) or {}

    # Merge env: existing values, with our overrides taking precedence.
    existing_env = cfg.get("Env") or []
    env: dict[str, str] = {}
    for entry in existing_env:
        if "=" in entry:
            k, v = entry.split("=", 1)
            env[k] = v
    env.update(cleaned)
    env_list = [f"{k}={v}" for k, v in env.items()]

    existing_image = cfg.get("Image") or ""
    if image_tag is not None:
        java_tag = next((t for t in JAVA_TAGS if t["tag"] == image_tag), None)
        if java_tag is None:
            raise RuntimeError_(f"Unknown Java image tag: {image_tag}")
        # Resolve to a concrete MC version for the compat check. Use the new
        # VERSION if the user is changing it; otherwise use the existing env.
        target_mc_raw = cleaned.get("VERSION") or env.get("VERSION", "")
        # Local import to avoid a circular at module-load.
        try:
            from mods.mojang import resolve as _resolve_mc
            target_mc = _resolve_mc(target_mc_raw) or target_mc_raw
        except Exception:  # noqa: BLE001
            target_mc = target_mc_raw
        if java_tag["java"] > 0 and target_mc:
            required = min_java_for_mc(target_mc)
            if java_tag["java"] < required:
                raise RuntimeError_(
                    f"Java {java_tag['java']} is too old for Minecraft {target_mc} "
                    f"— requires Java {required} or newer."
                )
        image = f"{IMAGE_REPO}:{image_tag}"
    else:
        image = existing_image
    name = settings.MC_CONTAINER_NAME

    # Pre-pull the target image BEFORE we tear down the old container. If the
    # tag doesn't exist locally and the proxy can't pull it, ``containers.create``
    # later would 404 — and we'd be left with no MC container at all (we
    # already removed the old one). Pulling up-front lets us bail cleanly,
    # leaving the existing container untouched.
    if image_tag is not None and image != existing_image:
        # Long timeout: itzg's per-Java images are ~500 MB on a cold pull.
        pull_client = docker.DockerClient(base_url=settings.DOCKER_HOST, timeout=600)
        try:
            pull_client.images.pull(image)
        except (APIError, DockerException) as exc:
            raise RuntimeError_(
                f"Couldn't pull image {image}: {exc}. Check that the docker-socket-proxy "
                f"exposes IMAGES=1 and POST=1, and that the host has internet access."
            ) from exc
        finally:
            try:
                pull_client.close()
            except Exception:  # noqa: BLE001
                pass
    labels = cfg.get("Labels") or {}
    cmd = cfg.get("Cmd")  # None preserves the image's default

    # Networks (preserve aliases). Connect after creation for any beyond the first.
    networks = network_settings.get("Networks") or {}
    primary_net = next(iter(networks), None)

    # Preserve static IPs declared in compose (``ipv4_address``) — the
    # high-level ``containers.run`` doesn't accept per-network IPAM, so
    # we read the desired address off ``IPAMConfig.IPv4Address`` and
    # reapply it via ``network.connect(... ipv4_address=...)`` after the
    # container is created. Without this, every apply_overrides would
    # bump the MC container to a fresh dynamic IP — which breaks any
    # external service the user pointed at it (Playit, custom firewall
    # rules, etc.).
    static_ips: dict[str, str] = {}
    for net_name, net in networks.items():
        ip = ((net or {}).get("IPAMConfig") or {}).get("IPv4Address", "")
        if ip:
            static_ips[net_name] = ip

    binds = host_cfg.get("Binds") or []
    # Merge user-managed allocations into the existing port bindings. Anything
    # the network app declares wins over a stale binding for the same key.
    port_bindings = dict(host_cfg.get("PortBindings") or {})
    port_bindings.update(extra_port_bindings)
    restart_policy = host_cfg.get("RestartPolicy") or {"Name": "unless-stopped"}
    security_opt = host_cfg.get("SecurityOpt") or []
    cap_add = host_cfg.get("CapAdd") or None
    cap_drop = host_cfg.get("CapDrop") or None

    # Stop + remove the old one. Server stop has its own ~60s timeout for graceful save.
    if container.status == "running":
        try:
            container.stop(timeout=60)
        except APIError as exc:
            logger.warning("graceful stop failed, killing: %s", exc)
            container.kill()
    container.remove(force=True)

    # Engine swap → reset the data dir BEFORE the new container starts,
    # otherwise itzg's bootstrap is racing with our deletes. The user
    # signed off on this in the pre-apply dialog and has the full safety
    # backup to recover anything they care about.
    if engine_reset:
        removed = _wipe_engine_reset()
        logger.info("engine reset: wiped %d top-level entries from MC_DATA_PATH", removed)

    # Create with no network attached, then connect explicitly so we can
    # honor any static IPv4 addresses recorded above.
    new_container = client.containers.create(
        image,
        name=name,
        environment=env_list,
        command=cmd,
        volumes=binds,
        ports=port_bindings,
        restart_policy=restart_policy,
        security_opt=security_opt,
        cap_add=cap_add,
        cap_drop=cap_drop,
        labels=labels,
        network_mode="none",
    )

    # Disconnect from the "none" placeholder and attach to each real
    # network. If we recorded a static IPv4 for this network in the old
    # container, pass it through here.
    try:
        client.networks.get("none").disconnect(new_container, force=True)
    except (NotFound, APIError):
        pass

    attached_any = False
    last_attach_error: Exception | None = None
    for net_name in networks.keys():
        try:
            kwargs: dict = {}
            if net_name in static_ips:
                kwargs["ipv4_address"] = static_ips[net_name]
            client.networks.get(net_name).connect(new_container, **kwargs)
            attached_any = True
        except (NotFound, APIError) as exc:
            logger.warning("could not attach to network %s: %s", net_name, exc)
            last_attach_error = exc

    # Safety net — never leave the container on Docker's special "none"
    # network when it's supposed to talk to the panel and reach the
    # internet. Most often this is the docker-socket-proxy missing
    # NETWORKS=1; surface a clear error and clean up so the operator can
    # re-run after fixing compose, rather than getting stuck with a
    # container that has no DNS.
    if networks and not attached_any:
        try:
            new_container.remove(force=True)
        except APIError:
            pass
        raise RuntimeError_(
            f"Couldn't reattach the container to any network "
            f"({last_attach_error}). Add NETWORKS=1 to the docker-socket-proxy "
            f"env, then try again."
        )

    new_container.start()

    # Recreate the Playit sidecar against the fresh MC netns (its old one
    # disappeared with the previous container).
    try:
        from network import agent
        agent.restart_if_was_running()
    except Exception:  # noqa: BLE001
        logger.exception("could not respawn playit agent after MC recreate")

    return snapshot()
