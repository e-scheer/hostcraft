"""Tiny client for playit.gg's agent API.

The agent secret the user pasted is enough to query their tunnels — no
OAuth dance, no cookie. We hit ``POST /agents/rundata`` and pull the
assigned hostname out of the response. The agent itself uses this same
endpoint internally on startup, so we get the truth without waiting for
log lines to scroll past.

Endpoint reference: https://github.com/playit-cloud/playit-agent
(packages/agent_core/src/api/api.rs)
"""

from __future__ import annotations

import logging

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

API_BASE = "https://api.playit.gg"
TIMEOUT = 6
# 5 min — the assigned hostname doesn't change often once a tunnel is set
# up, so don't hammer playit.gg on every dashboard tick. The agent itself
# already pings them several times a minute and gets rate-limited; piling
# on from the panel side just makes things worse.
CACHE_TTL = 300


def _cache_key(secret: str) -> str:
    # Don't put the raw secret into the cache key. A short prefix is enough
    # to uniquely identify the user's tunnel set without leaking the
    # secret if cache is ever inspected.
    return f"playit:rundata:{secret[:12]}"


def _post(path: str, secret: str) -> dict | None:
    try:
        resp = requests.post(
            f"{API_BASE}{path}",
            json={},
            headers={
                "Authorization": f"agent-key {secret}",
                "Accept": "application/json",
                "User-Agent": "hostcraft/1.0",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        log.info("playit API unreachable: %s", exc)
        return None
    if resp.status_code in (401, 403):
        log.info("playit API auth failed (%s) — secret invalid?", resp.status_code)
        return None
    if not resp.ok:
        log.info("playit API %s → %s: %s", path, resp.status_code, resp.text[:120])
        return None
    try:
        return resp.json()
    except ValueError:
        return None


_NEGATIVE_CACHE_TTL = 60  # seconds — when the API returns nothing, don't
                          # immediately retry; that's how we get 429s.


def lookup_tunnels(secret: str, *, force: bool = False) -> list[dict] | None:
    """Return the list of tunnels for ``secret``.

    - ``[...]`` — populated tunnel list
    - ``[]``    — secret is valid, but no tunnel configured (yet)
    - ``None``  — API call itself failed (network, auth, rate limit)

    Cached aggressively (see ``CACHE_TTL``) — the assigned hostname is
    stable once configured, and Playit rate-limits per agent key.
    """
    if not secret:
        return None
    key = _cache_key(secret)
    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached

    data = _post("/agents/rundata", secret)
    if data is None:
        # Negative-cache so callers don't immediately retry. Distinct value
        # from "" so we can tell "API down" apart from "0 tunnels".
        cache.set(key, None, _NEGATIVE_CACHE_TTL)
        return None
    raw = data.get("data") or data
    tunnels = raw.get("tunnels") or []
    if not isinstance(tunnels, list):
        tunnels = []
    # When the agent is configured but has no tunnel yet, the user is
    # likely in the middle of setting one up on playit.gg — don't lock
    # them into a 5 min stale view. Re-check every minute until at least
    # one tunnel shows up.
    ttl = CACHE_TTL if tunnels else _NEGATIVE_CACHE_TTL
    cache.set(key, tunnels, ttl)
    return tunnels


def primary_hostname(secret: str, *, force: bool = False) -> str:
    """Best guess for the user's "main" Minecraft tunnel hostname.

    Picks the first TCP tunnel whose ``port`` matches Minecraft's default
    25565, falling back to the first tunnel of any kind. Returns ``""``
    when no tunnel is configured or the API is unreachable.
    """
    tunnels = lookup_tunnels(secret, force=force)
    if not tunnels:
        return ""

    def host_of(t: dict) -> str:
        return (t.get("custom_domain") or t.get("assigned_domain") or "").strip()

    # Prefer TCP tunnels on 25565 — that's the Minecraft default.
    mc = [
        t for t in tunnels
        if str(t.get("proto", "")).lower() in ("tcp", "both")
        and int(t.get("port", 0)) == 25565
    ]
    for t in mc:
        h = host_of(t)
        if h:
            return h
    for t in tunnels:
        h = host_of(t)
        if h:
            return h
    return ""


def setup_state(secret: str) -> str:
    """Quick check on whether the secret has a usable tunnel.

    - ``ready``     — at least one tunnel is configured
    - ``no_tunnel`` — secret is valid, but the user hasn't created a
                     tunnel on playit.gg yet
    - ``unknown``   — API unreachable or auth failed
    """
    tunnels = lookup_tunnels(secret)
    if tunnels is None:
        return "unknown"
    if len(tunnels) == 0:
        return "no_tunnel"
    return "ready"
