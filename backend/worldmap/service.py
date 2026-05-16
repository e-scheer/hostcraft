"""World map setup — wraps BlueMap install behind a one-click flow.

BlueMap is the only web map we offer today. It supports every engine
hostcraft can manage (Forge / NeoForge / Fabric / Paper / Purpur / Spigot)
and ships its own HTTP server on port 8100. We:

- detect whether the BlueMap .jar is already on disk (idempotent setup)
- install it via the marketplace path (``mods.installer.install``) so the
  user benefits from the same loader-aware version picking
- open port 8100 by creating a ``network.Allocation`` — that triggers the
  same container recreate the marketplace uses for other allocations

The browser iframe just points at the host machine's port 8100. For
remote setups, the user adds a Playit tunnel or DNS allocation for it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from mods import installer as mods_installer
from mods.loader import Target, detect
from network import service as network_service
from network.models import Allocation

logger = logging.getLogger(__name__)

# The Modrinth project slug works for every loader — BlueMap publishes
# all variants (Paper, Fabric, Forge, NeoForge, Sponge) under a single
# project, and Modrinth's filter on (loader, mc_version) picks the right
# .jar at install time.
BLUEMAP_PROJECT_ID = "bluemap"
BLUEMAP_PORT = 8100
WEBSERVER_LABEL = "BlueMap web map"

# BlueMap bumped its baseline Java version twice: 4.x was the first to require
# Java 17, 5.x moved to Java 21. Trying to load a too-new jar on an older
# Java prevents the *whole* mod loader from booting (classfile version error
# in Forge's ServerModLoader, hard crash-loop). So we pick the newest BlueMap
# major that the running container's Java can actually load.
_BLUEMAP_MIN_JAVA = {
    5: 21,
    4: 17,
    3: 16,
    2: 8,
    1: 8,
}


@dataclass(frozen=True)
class WorldmapStatus:
    state: str            # 'unsupported' | 'not_installed' | 'installed'
    filename: str = ""    # installed jar basename, when present
    web_port: int = BLUEMAP_PORT
    target_kind: str = "" # 'mod' | 'plugin' | 'none'
    target_loader: str = ""


def status() -> WorldmapStatus:
    t = detect()
    if t.kind not in ("mod", "plugin"):
        return WorldmapStatus(state="unsupported", target_kind=t.kind, target_loader=t.loader_label)

    folder = "mods" if t.kind == "mod" else "plugins"
    jar = _find_bluemap_jar(Path(settings.MC_DATA_PATH) / folder)
    if jar is None:
        return WorldmapStatus(state="not_installed", target_kind=t.kind, target_loader=t.loader_label)
    return WorldmapStatus(
        state="installed",
        filename=jar.name,
        target_kind=t.kind,
        target_loader=t.loader_label,
    )


def _find_bluemap_jar(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    for f in folder.iterdir():
        if not f.is_file() or f.suffix.lower() != ".jar":
            continue
        if f.name.lower().startswith("bluemap"):
            return f
    return None


def install_bluemap() -> dict:
    """Install BlueMap + open port 8100 + auto-accept asset download.

    Fully idempotent — calling this on a partial install (jar present
    but port not published, or config still set to accept-download:
    false) brings everything into a working state.
    """
    t = detect()
    if t.kind not in ("mod", "plugin"):
        raise ValueError(
            f"Engine '{t.loader_label}' doesn't support BlueMap."
        )
    folder = "mods" if t.kind == "mod" else "plugins"

    # 1. Drop the jar via the marketplace path (loader-aware picker).
    #    If the .jar is already on disk we still re-run for the upsert.
    existing_jar = _find_bluemap_jar(Path(settings.MC_DATA_PATH) / folder)
    if existing_jar is None:
        # Pin to a BlueMap major compatible with the container's Java.
        version_id = _pick_bluemap_version_id(t)
        result = mods_installer.install(
            "modrinth", BLUEMAP_PROJECT_ID, version_id=version_id,
        )
        installed_filename = result.record.filename
        verified = result.verified
    else:
        installed_filename = existing_jar.name
        verified = True

    # 2. Pre-accept the BlueMap asset download. The plugin would
    #    otherwise refuse to fetch Minecraft textures on first boot and
    #    park itself in a "missing resources" state, breaking the
    #    webserver. We write the minimal config it expects; BlueMap
    #    merges with its bundled defaults.
    _ensure_accept_download(t.kind)

    # 3. Make sure port 8100 is in the allocation list.
    Allocation.objects.update_or_create(
        host_port=BLUEMAP_PORT,
        protocol="tcp",
        defaults={
            "container_port": BLUEMAP_PORT,
            "label": WEBSERVER_LABEL,
            "notes": "Auto-added when BlueMap was installed.",
        },
    )

    # 4. ALWAYS sync (recreate container with current bindings). The
    #    previous behaviour only synced when the allocation was new —
    #    that left users stuck whenever the container had been recreated
    #    via ``compose up`` (which drops dynamic port bindings).
    try:
        network_service.sync_to_container()
    except Exception:  # noqa: BLE001
        logger.exception("could not sync allocations after BlueMap install")

    return {
        "filename": installed_filename,
        "verified": verified,
        "port": BLUEMAP_PORT,
    }


def _bluemap_config_dir(kind: str) -> Path:
    """Where the BlueMap plugin/mod reads its HOCON configs from.

    BlueMap's path depends on the loader family:
    - Bukkit family (Paper / Purpur / Spigot) → ``plugins/BlueMap/``
    - Forge / NeoForge / Fabric / Quilt       → ``config/bluemap/``

    Writing accept-download in the wrong place is a silent no-op: the
    plugin reads its real path, sees the bundled default
    (``accept-download: false``) and parks itself in a "missing
    resources" state — which is the bug we tripped on after engine
    swaps.
    """
    base = Path(settings.MC_DATA_PATH)
    if kind == "plugin":
        return base / "plugins" / "BlueMap"
    return base / "config" / "bluemap"


def _ensure_accept_download(kind: str) -> None:
    """Write a minimal BlueMap config that auto-accepts asset download.

    Idempotent — if the file already exists we surgically rewrite the
    ``accept-download`` line; otherwise we create it from scratch.
    """
    cfg_dir = _bluemap_config_dir(kind)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "core.conf"
    if cfg.exists():
        try:
            text = cfg.read_text(encoding="utf-8")
        except OSError:
            return
        new_text, n = _flip_accept_download(text)
        if n == 0:
            new_text = text.rstrip() + "\n\naccept-download: true\n"
        if new_text != text:
            cfg.write_text(new_text, encoding="utf-8")
        return
    cfg.write_text(
        "# Auto-generated by hostcraft so BlueMap can fetch its assets.\n"
        "accept-download: true\n",
        encoding="utf-8",
    )


def _flip_accept_download(text: str) -> tuple[str, int]:
    """Set ``accept-download`` to true wherever it appears in HOCON."""
    import re
    pattern = re.compile(
        r"^(\s*accept-download\s*[:=]\s*)(false|true)\s*$",
        re.MULTILINE,
    )
    return pattern.subn(lambda m: f"{m.group(1)}true", text)


def _current_java_major() -> int:
    """Best-effort: which Java major is the running MC container using?

    Reads the explicit itzg ``javaXX`` tag if set. ``latest`` lets itzg
    auto-pick the newest available Java (today: Java 25) — we mirror that
    here so we don't accidentally install a BlueMap that's too old.
    """
    from server.runtime import snapshot, parse_image_tag, JAVA_TAGS
    snap = snapshot()
    tag = parse_image_tag(snap.image)
    for jt in JAVA_TAGS:
        if jt["tag"] == tag and jt["java"] > 0:
            return int(jt["java"])
    return 25


def _pick_bluemap_version_id(target: Target) -> str | None:
    """Pick the newest BlueMap version Modrinth offers that:

    - matches the current MC version and loader (Modrinth filters those),
    - has a major whose minimum Java requirement is satisfied by the
      container's Java.

    Returns ``None`` if Modrinth lookup fails — falls back to the
    installer's default "newest compat" picker, which is fine on
    Java 21+ but will reproduce the crash on Java 17. We log so an
    operator can tell what happened.
    """
    from mods.providers import modrinth
    from mods.loader import current_mc_version

    java_major = _current_java_major()
    try:
        candidates = modrinth.versions(
            BLUEMAP_PROJECT_ID,
            loaders=target.loaders or None,
            mc_versions=None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("modrinth lookup failed for BlueMap version pin")
        return None

    if not candidates:
        return None

    mc = (current_mc_version() or "").upper()
    compatible = []
    for v in candidates:
        # MC version filter (mirror installer._pick_version).
        if mc and v.mc_versions and mc not in [m.upper() for m in v.mc_versions]:
            continue
        # Major from "5.12-mc1.20-6" → 5.
        first = v.version_number.split(".", 1)[0]
        try:
            major = int(first)
        except ValueError:
            continue
        required_java = _BLUEMAP_MIN_JAVA.get(major, 21)
        if required_java <= java_major:
            compatible.append(v)

    if not compatible:
        logger.warning(
            "no BlueMap version compatible with Java %d for MC %s; "
            "letting installer pick the default (likely to fail to load)",
            java_major, mc,
        )
        return None
    return compatible[0].version_id
