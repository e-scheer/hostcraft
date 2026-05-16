"""Detect what kind of mod/plugin runs on the configured server.

Reads the runtime ``TYPE`` env (set in ``backend/server/runtime.py``) and
maps it to a target folder + canonical loader vocabulary.

This is the single source of truth used by both ``service.unified_search``
(to filter by compatibility) and ``installer`` (to pick the destination).
"""

from __future__ import annotations

from dataclasses import dataclass

from server import runtime as server_runtime
from . import mojang


@dataclass(frozen=True)
class Target:
    kind: str           # 'mod' | 'plugin' | 'none'
    folder: str         # 'mods' | 'plugins' | ''
    loaders: list[str]  # canonical loader names this server accepts
    loader_label: str   # human-friendly: "Paper", "Fabric", …


_TYPE_MAP: dict[str, Target] = {
    # Modded
    "FORGE":     Target("mod", "mods", ["forge"], "Forge"),
    "NEOFORGE":  Target("mod", "mods", ["neoforge"], "NeoForge"),
    "FABRIC":    Target("mod", "mods", ["fabric"], "Fabric"),
    "QUILT":     Target("mod", "mods", ["quilt", "fabric"], "Quilt"),
    # Plugins (Bukkit family)
    "PAPER":     Target("plugin", "plugins", ["paper", "spigot", "bukkit"], "Paper"),
    "PURPUR":    Target("plugin", "plugins", ["purpur", "paper", "spigot", "bukkit"], "Purpur"),
    "SPIGOT":    Target("plugin", "plugins", ["spigot", "bukkit"], "Spigot"),
    "BUKKIT":    Target("plugin", "plugins", ["bukkit"], "Bukkit"),
    "FOLIA":     Target("plugin", "plugins", ["folia", "paper", "spigot", "bukkit"], "Folia"),
    # Vanilla can't take any of these.
    "VANILLA":   Target("none", "", [], "Vanilla"),
}


def detect() -> Target:
    """Return the target for the currently-configured server type."""
    snap = server_runtime.snapshot()
    raw = (snap.env or {}).get("TYPE", "")
    upper = (raw or "").upper().strip()
    return _TYPE_MAP.get(upper, Target("none", "", [], raw or "Unknown"))


def current_mc_version() -> str:
    """Concrete MC version the server runs, resolving ``LATEST``/``SNAPSHOT``.

    When the configured value is ``LATEST`` (itzg's default), we ask Mojang's
    manifest for the actual version. Falls back to the raw value if Mojang
    is unreachable.
    """
    snap = server_runtime.snapshot()
    raw = (snap.env or {}).get("VERSION", "") or ""
    return mojang.resolve(raw) or raw


def configured_version_alias() -> str:
    """The raw VERSION env (e.g. 'LATEST'), useful for UI hints."""
    snap = server_runtime.snapshot()
    return (snap.env or {}).get("VERSION", "") or ""
