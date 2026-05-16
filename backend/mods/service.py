"""Aggregator that merges results from multiple providers.

The frontend sends one query; we fan out to providers in parallel-ish
(sequentially for now, providers are cached so it's cheap on second call)
and zip the hits together. Each provider's results are tagged so the UI
can show a "Modrinth"/"Hangar" badge.

We also surface compatibility info from ``loader.detect()`` so the UI can
hide projects that don't run on the current server (Bukkit plugins on a
Fabric mod server, etc.).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .loader import Target, configured_version_alias, current_mc_version, detect
from .providers import ProviderError, SearchHit, SearchPage, hangar, modrinth

log = logging.getLogger(__name__)


def unified_search(
    query: str,
    *,
    limit: int = 24,
    offset: int = 0,
    target: Target | None = None,
    mc_version: str | None = None,
    strict_version: bool = True,
) -> dict:
    """Search providers compatible with ``target`` and merge results.

    When ``target`` is ``None``, we use whatever the server is configured
    for. Pass an explicit ``Target`` to override (useful for testing).

    When ``strict_version`` is False, the MC-version filter is dropped so
    the UI can show the user projects that haven't (yet) declared support
    for the running version.
    """
    target = target or detect()
    mc_version = mc_version or current_mc_version()
    # Empty string when the user runs LATEST and Mojang's manifest is
    # unreachable — in that case we just don't filter by MC version.
    versions = [mc_version] if mc_version and strict_version else []

    sources: list[tuple[str, callable]] = []

    if target.kind == "mod":
        # Modded servers see both standalone mods AND modpacks. Modpacks
        # bundle a tested set of mods so we surface them so the user can
        # pick the safer "curated" route (install path itself is mod-only
        # for now — modpack install is handled separately).
        sources.append(
            ("modrinth", lambda: modrinth.search(
                query,
                loaders=target.loaders,
                mc_versions=versions,
                project_types=["mod", "modpack"],
                server_side_required=True,
                limit=limit,
                offset=offset,
            ))
        )
    elif target.kind == "plugin":
        # Modrinth has plugins too — and recent Paper plugins live there
        # alongside Hangar.
        sources.append(
            ("modrinth", lambda: modrinth.search(
                query,
                loaders=target.loaders,
                mc_versions=versions,
                project_types=["plugin"],
                server_side_required=True,
                limit=limit,
                offset=offset,
            ))
        )
        sources.append(
            ("hangar", lambda: hangar.search(
                query,
                loaders=target.loaders,
                mc_versions=versions,
                limit=limit,
                offset=offset,
            ))
        )
    else:
        # Vanilla / unknown — nothing installable
        return {
            "hits": [],
            "total": 0,
            "providers_errored": [],
            "target": _target_dict(target, mc_version),
        }

    hits: list[SearchHit] = []
    total = 0
    errored: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        futures = {ex.submit(fn): name for name, fn in sources}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                page: SearchPage = fut.result()
            except ProviderError as exc:
                log.info("Provider %s failed: %s", name, exc)
                errored.append({"provider": name, "error": str(exc)})
                continue
            hits.extend(page.hits)
            total += page.total

    # Stable, downloads-desc sort across providers.
    hits.sort(key=lambda h: h.downloads, reverse=True)

    # Enrich with truthful per-version compat info (responses are cached
    # for an hour at the provider layer, so repeat searches are cheap).
    _enrich_compat(hits, target, mc_version)

    return {
        "hits": [h.to_dict() for h in hits],
        "total": total,
        "providers_errored": errored,
        "target": _target_dict(target, mc_version),
    }


def _enrich_compat(hits: list[SearchHit], target: Target, mc_version: str) -> None:
    """Annotate each hit with ``installable_for_target`` + supported MC list.

    Project-level metadata (the ``versions`` array on a search hit) is the
    union over all the project's files: a Modrinth project that has a
    Fabric build for 1.21 and a Forge build for 1.20 will list both, even
    though the Forge user can't actually install on 1.21. This walker
    fetches each hit's per-file versions and computes the truthful answer
    for *this server's* (loader, mc).
    """
    if target.kind == "none" or not hits:
        return

    loaders = target.loaders or []

    def fetch(h: SearchHit):
        try:
            if h.provider == "modrinth":
                return modrinth.versions(h.project_id, loaders=loaders or None)
            if h.provider == "hangar":
                return hangar.versions(h.project_id)
        except ProviderError as exc:
            log.debug("compat fetch failed for %s/%s: %s",
                      h.provider, h.project_id, exc)
        return []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch, h): h for h in hits}
        for fut in as_completed(futures):
            h = futures[fut]
            versions = fut.result() or []
            # Versions whose loader matches ours (or that don't declare any).
            loader_compat = [
                v for v in versions
                if not loaders
                or not v.loaders
                or any(l in loaders for l in v.loaders)
            ]
            # Of those, which support the running MC version?
            installable_versions = [
                v for v in loader_compat
                if not mc_version or not v.mc_versions
                or mc_version in v.mc_versions
            ]
            h.installable_for_target = len(installable_versions) > 0
            mc_set = {
                m for v in loader_compat
                for m in v.mc_versions
                if _looks_like_release(m)
            }
            h.compat_mc_versions_for_loader = sorted(mc_set, key=_version_key)


def _looks_like_release(v: str) -> bool:
    parts = v.split(".")
    return all(p.isdigit() for p in parts) and 2 <= len(parts) <= 4


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def fetch_versions(provider: str, project_id: str, *, target: Target | None = None,
                   mc_version: str | None = None) -> list[dict]:
    target = target or detect()
    mc_version = mc_version or current_mc_version()
    versions_filter = [mc_version] if mc_version else None
    loaders_filter = target.loaders or None

    if provider == "modrinth":
        out = modrinth.versions(project_id, loaders=loaders_filter, mc_versions=versions_filter)
    elif provider == "hangar":
        out = hangar.versions(project_id, loaders=loaders_filter, mc_versions=versions_filter)
    else:
        raise ProviderError(f"Unknown provider: {provider}")
    return [v.to_dict() for v in out]


def _target_dict(t: Target, mc_version: str) -> dict:
    alias = configured_version_alias()
    return {
        "kind": t.kind,
        "folder": t.folder,
        "loaders": list(t.loaders),
        "loader_label": t.loader_label,
        "mc_version": mc_version,
        "mc_version_alias": alias if alias and alias.upper() != mc_version.upper() else "",
    }
