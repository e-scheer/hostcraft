"""Resolve Minecraft version aliases via Mojang's official manifest.

We hit ``piston-meta.mojang.com``'s public manifest — the same data the
launcher uses — so when itzg/minecraft-server is configured with
``VERSION=LATEST`` we can still tell the marketplace which real MC version
is running, and filter results accordingly.

Cached aggressively (6 h) — Mojang publishes a new release at most a few
times a year.
"""

from __future__ import annotations

import logging

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
CACHE_KEY = "mojang:manifest"
CACHE_TTL = 6 * 3600
TIMEOUT = 6


def _manifest() -> dict | None:
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    try:
        resp = requests.get(MANIFEST_URL, timeout=TIMEOUT,
                            headers={"User-Agent": "hostcraft/1.0"})
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.info("Mojang manifest unreachable: %s", exc)
        return None
    cache.set(CACHE_KEY, data, CACHE_TTL)
    return data


def latest_release() -> str | None:
    """Latest stable MC version (e.g. '1.21.4') or None if Mojang is unreachable."""
    m = _manifest()
    if not m:
        return None
    return (m.get("latest") or {}).get("release")


def resolve(version: str) -> str:
    """Map ``version`` to a concrete MC version string.

    - ``LATEST`` / ``latest`` → latest stable release (or '' if Mojang is down)
    - ``LATEST_SNAPSHOT`` / ``snapshot`` → latest snapshot
    - everything else → returned as-is
    """
    raw = (version or "").strip()
    upper = raw.upper()
    if upper in ("LATEST", "RELEASE"):
        return latest_release() or ""
    if upper in ("LATEST_SNAPSHOT", "SNAPSHOT"):
        m = _manifest()
        return (m.get("latest") or {}).get("snapshot", "") if m else ""
    return raw
