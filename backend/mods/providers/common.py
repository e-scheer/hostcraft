"""Shared types for marketplace providers.

Each provider returns the same shape so the aggregator can merge results
without knowing the source.

Loader vocabulary (canonical, lower-case):
    forge, neoforge, fabric, quilt, paper, spigot, bukkit, purpur, folia, sponge

Project kind:
    mod    — runs on a modded server (Forge/NeoForge/Fabric/Quilt)
    plugin — runs on a Bukkit-API server (Paper/Purpur/Spigot/Bukkit/Folia)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


class ProviderError(Exception):
    """Provider couldn't fulfil the request (network, schema, etc.)."""


DependencyKind = Literal["required", "optional", "incompatible", "embedded"]


@dataclass
class Dependency:
    project_id: str
    version_id: str | None
    kind: DependencyKind
    name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchHit:
    provider: str
    project_id: str          # provider-specific stable id (or slug for Hangar)
    slug: str
    title: str
    summary: str
    icon_url: str
    project_url: str
    downloads: int
    follows: int
    project_type: str = "mod"          # 'mod' | 'plugin' | 'modpack' | 'datapack' | …
    server_side: str = "unknown"       # 'required' | 'optional' | 'unsupported' | 'unknown'
    client_side: str = "unknown"
    categories: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    mc_versions: list[str] = field(default_factory=list)
    # Filled in by ``service._enrich_compat`` after the per-version fetch.
    # Project-level metadata over-promises compat (a project can list 1.21
    # because its Fabric file supports it, while its Forge file maxes out
    # at 1.20). These fields are the truthful per-loader signal.
    installable_for_target: bool | None = None
    compat_mc_versions_for_loader: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchPage:
    hits: list[SearchHit]
    total: int


HashAlgo = Literal["sha512", "sha256", ""]


@dataclass
class VersionInfo:
    provider: str
    project_id: str
    version_id: str
    name: str
    version_number: str
    file_url: str
    filename: str
    file_size: int
    file_hash: str          # hex digest, empty if absent
    hash_algo: HashAlgo     # which algo `file_hash` is in
    mc_versions: list[str]
    loaders: list[str]
    dependencies: list[Dependency]
    published_at: str  # ISO

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dependencies"] = [dep.to_dict() if isinstance(dep, Dependency) else dep
                             for dep in self.dependencies]
        return d
