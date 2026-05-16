"""Modrinth provider — covers Forge/Fabric/Quilt mods + Bukkit-family plugins.

Docs: https://docs.modrinth.com/api/

We hit the public v2 API. No API key needed. We send a polite User-Agent
since Modrinth's docs request it.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable
from urllib.parse import quote

import requests
from django.core.cache import cache

from .common import (
    Dependency,
    ProviderError,
    SearchHit,
    SearchPage,
    VersionInfo,
)

log = logging.getLogger(__name__)

BASE = "https://api.modrinth.com/v2"
USER_AGENT = "hostcraft (https://github.com/escheer/hostcraft)"
TIMEOUT = 10
CACHE_TTL = 3600


def _get(path: str, params: dict | None = None) -> dict | list:
    import hashlib
    url = f"{BASE}{path}"
    payload = json.dumps(params, sort_keys=True) if params else ""
    cache_key = f"modrinth:{path}:{hashlib.sha1(payload.encode()).hexdigest()[:12]}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ProviderError(f"Modrinth network error: {exc}") from exc
    if resp.status_code == 404:
        raise ProviderError("Modrinth: project not found.")
    if not resp.ok:
        raise ProviderError(f"Modrinth HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError(f"Modrinth: invalid JSON response: {exc}") from exc
    cache.set(cache_key, data, CACHE_TTL)
    return data


def _facets(
    loaders: Iterable[str],
    mc_versions: Iterable[str],
    project_types: Iterable[str] | None,
    server_side_required: bool,
) -> list[list[str]] | None:
    """Build Modrinth's facet array from filter lists.

    Modrinth wants `facets=[["categories:fabric"],["versions:1.21.4"]]` —
    each inner array is OR-ed, the outer array is AND-ed.
    """
    facets: list[list[str]] = []
    if loaders:
        facets.append([f'categories:{l}' for l in loaders])
    if mc_versions:
        facets.append([f'versions:{v}' for v in mc_versions])
    if project_types:
        facets.append([f'project_type:{pt}' for pt in project_types])
    if server_side_required:
        # Exclude `unsupported` server-side projects. Modrinth doesn't
        # support negation, so we OR the acceptable values.
        facets.append([
            "server_side:required",
            "server_side:optional",
            "server_side:unknown",
        ])
    return facets or None


def search(
    query: str,
    *,
    loaders: list[str] | None = None,
    mc_versions: list[str] | None = None,
    project_types: list[str] | None = None,
    server_side_required: bool = True,
    limit: int = 24,
    offset: int = 0,
) -> SearchPage:
    """Search projects.

    project_types: list of 'mod' | 'plugin' | 'modpack' | 'datapack' | …
                   Pass None to leave unfiltered. Multiple values OR-ed.
    server_side_required: when True, drop projects whose ``server_side``
                          metadata is ``unsupported`` (client-only mods).
    """
    params: dict = {"limit": limit, "offset": offset, "index": "relevance"}
    if query.strip():
        params["query"] = query.strip()
    facets = _facets(loaders or [], mc_versions or [], project_types, server_side_required)
    if facets:
        params["facets"] = json.dumps(facets)

    data = _get("/search", params=params)
    if not isinstance(data, dict):
        raise ProviderError("Modrinth: unexpected search payload.")

    hits: list[SearchHit] = []
    for h in data.get("hits", []):
        ptype = h.get("project_type", "mod")
        hits.append(
            SearchHit(
                provider="modrinth",
                project_id=h.get("project_id") or h.get("id") or h["slug"],
                slug=h["slug"],
                title=h.get("title", h["slug"]),
                summary=h.get("description", "") or "",
                icon_url=h.get("icon_url") or "",
                project_url=f"https://modrinth.com/{ptype}/{h['slug']}",
                downloads=int(h.get("downloads", 0)),
                follows=int(h.get("follows", 0)),
                project_type=ptype,
                server_side=h.get("server_side", "unknown") or "unknown",
                client_side=h.get("client_side", "unknown") or "unknown",
                categories=list(h.get("categories") or []) + list(h.get("display_categories") or []),
                loaders=[c for c in (h.get("categories") or []) if c in _ALL_LOADERS],
                mc_versions=list(h.get("versions") or []),
            )
        )
    return SearchPage(hits=hits, total=int(data.get("total_hits", len(hits))))


def versions(project_id: str, *, loaders: list[str] | None = None,
             mc_versions: list[str] | None = None) -> list[VersionInfo]:
    """List versions for a project, newest first.

    Modrinth supports filter params:
        loaders=["fabric"]&game_versions=["1.21.4"]
    """
    params: dict = {}
    if loaders:
        params["loaders"] = json.dumps(loaders)
    if mc_versions:
        params["game_versions"] = json.dumps(mc_versions)

    data = _get(f"/project/{quote(project_id)}/version", params=params)
    if not isinstance(data, list):
        raise ProviderError("Modrinth: unexpected versions payload.")

    out: list[VersionInfo] = []
    for v in data:
        files = v.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if primary is None:
            continue
        deps = [
            Dependency(
                project_id=d.get("project_id") or "",
                version_id=d.get("version_id"),
                kind=d.get("dependency_type", "required"),
                name=d.get("project_id") or "",
            )
            for d in (v.get("dependencies") or [])
        ]
        out.append(
            VersionInfo(
                provider="modrinth",
                project_id=v.get("project_id", project_id),
                version_id=v["id"],
                name=v.get("name", v.get("version_number", "")),
                version_number=v.get("version_number", ""),
                file_url=primary["url"],
                filename=primary["filename"],
                file_size=int(primary.get("size", 0)),
                file_hash=(primary.get("hashes") or {}).get("sha512", ""),
                hash_algo="sha512" if (primary.get("hashes") or {}).get("sha512") else "",
                mc_versions=list(v.get("game_versions") or []),
                loaders=list(v.get("loaders") or []),
                dependencies=deps,
                published_at=v.get("date_published", ""),
            )
        )
    return out


_ALL_LOADERS = {
    "forge", "neoforge", "fabric", "quilt",
    "paper", "purpur", "spigot", "bukkit", "folia", "sponge",
}
