"""Hangar provider — official PaperMC plugin index.

Docs: https://hangar.papermc.io/api-docs/

Hangar covers Paper/Velocity/Waterfall plugins. We focus on PAPER. No API
key needed for read endpoints.
"""

from __future__ import annotations

import json
import logging
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

BASE = "https://hangar.papermc.io/api/v1"
PUBLIC = "https://hangar.papermc.io"
USER_AGENT = "hostcraft (https://github.com/escheer/hostcraft)"
TIMEOUT = 10
CACHE_TTL = 3600


def _get(path: str, params: dict | None = None) -> dict | list:
    import hashlib
    url = f"{BASE}{path}"
    payload = json.dumps(params, sort_keys=True) if params else ""
    cache_key = f"hangar:{path}:{hashlib.sha1(payload.encode()).hexdigest()[:12]}"
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
        raise ProviderError(f"Hangar network error: {exc}") from exc
    if resp.status_code == 404:
        raise ProviderError("Hangar: project not found.")
    if not resp.ok:
        raise ProviderError(f"Hangar HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError(f"Hangar: invalid JSON response: {exc}") from exc
    cache.set(cache_key, data, CACHE_TTL)
    return data


def search(
    query: str,
    *,
    loaders: list[str] | None = None,
    mc_versions: list[str] | None = None,
    limit: int = 24,
    offset: int = 0,
) -> SearchPage:
    """Search Hangar projects.

    Hangar uses ``platform`` (PAPER/VELOCITY/WATERFALL) and ``version``
    parameters. We map our generic ``loaders`` filter onto platform.
    """
    params: dict = {"limit": limit, "offset": offset, "sort": "-stars"}
    if query.strip():
        params["q"] = query.strip()

    # Loader → platform: any of our loaders that maps to Paper triggers PAPER.
    paper_loaders = {"paper", "purpur", "folia"}
    if loaders and any(l in paper_loaders for l in loaders):
        params["platform"] = "PAPER"

    if mc_versions:
        # Hangar only allows a single version filter at a time.
        params["version"] = mc_versions[0]

    data = _get("/projects", params=params)
    if not isinstance(data, dict):
        raise ProviderError("Hangar: unexpected search payload.")

    hits: list[SearchHit] = []
    for r in data.get("result", []):
        ns = r.get("namespace") or {}
        slug = ns.get("slug") or r.get("name", "")
        owner = ns.get("owner", "")
        stats = r.get("stats") or {}
        compat = (r.get("supportedPlatforms") or [])
        hits.append(
            SearchHit(
                provider="hangar",
                project_id=f"{owner}/{slug}",
                slug=slug,
                title=r.get("name", slug),
                summary=r.get("description", "") or "",
                icon_url=f"{PUBLIC}/api/v1/projects/{owner}/{slug}/icon" if owner and slug else "",
                project_url=f"{PUBLIC}/{owner}/{slug}" if owner and slug else "",
                downloads=int(stats.get("downloads", 0)),
                follows=int(stats.get("stars", 0)),
                categories=[r.get("category")] if r.get("category") else [],
                loaders=[p.lower() for p in compat] or ["paper"],
                mc_versions=[],
            )
        )
    return SearchPage(hits=hits, total=int((data.get("pagination") or {}).get("count", len(hits))))


def versions(project_id: str, *, loaders: list[str] | None = None,
             mc_versions: list[str] | None = None) -> list[VersionInfo]:
    """List versions. ``project_id`` is "owner/slug"."""
    if "/" not in project_id:
        raise ProviderError("Hangar project_id must be 'owner/slug'.")
    owner, slug = project_id.split("/", 1)

    data = _get(f"/projects/{quote(owner)}/{quote(slug)}/versions", params={"limit": 25})
    if not isinstance(data, dict):
        raise ProviderError("Hangar: unexpected versions payload.")

    out: list[VersionInfo] = []
    for v in data.get("result", []):
        downloads = v.get("downloads") or {}
        # Hangar returns one entry per platform; pick PAPER if available.
        platform_data = downloads.get("PAPER") or next(iter(downloads.values()), None)
        if not platform_data:
            continue
        file_info = platform_data.get("fileInfo") or {}
        # External downloads (project hosted on a different host) lack a direct URL.
        file_url = (
            platform_data.get("downloadUrl")
            or f"{PUBLIC}/api/v1/projects/{owner}/{slug}/versions/{quote(v['name'])}/PAPER/download"
        )
        platform_dependencies = (v.get("platformDependencies") or {}).get("PAPER", [])
        out.append(
            VersionInfo(
                provider="hangar",
                project_id=project_id,
                version_id=v.get("name", ""),
                name=v.get("name", ""),
                version_number=v.get("name", ""),
                file_url=file_url,
                filename=file_info.get("name", f"{slug}-{v.get('name','')}.jar"),
                file_size=int(file_info.get("sizeBytes", 0)),
                file_hash=file_info.get("sha256Hash", ""),
                hash_algo="sha256" if file_info.get("sha256Hash") else "",
                mc_versions=list(platform_dependencies),
                loaders=["paper"],
                dependencies=[
                    Dependency(
                        project_id=d.get("name", ""),
                        version_id=None,
                        kind="required" if d.get("required") else "optional",
                        name=d.get("name", ""),
                    )
                    for d in (v.get("pluginDependencies") or {}).get("PAPER", [])
                ],
                published_at=v.get("createdAt", ""),
            )
        )
    return out
