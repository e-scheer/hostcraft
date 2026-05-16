"""Detect the panel host's public IP — cached so we don't hammer ifconfig.me."""

from __future__ import annotations

import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "network:public_ip"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour


def detect(force: bool = False) -> str | None:
    """Return the host's public IPv4, or None if we can't tell."""
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached or None

    # Cascading fallbacks — if one provider is down, try the next.
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            req = Request(url, headers={"User-Agent": "hostcraft"})
            with urlopen(req, timeout=4) as resp:  # noqa: S310 — fixed URLs
                ip = resp.read().decode("utf-8").strip()
                if ip and ip.count(".") == 3:
                    cache.set(CACHE_KEY, ip, CACHE_TTL_SECONDS)
                    return ip
        except (URLError, TimeoutError, OSError) as exc:
            logger.debug("public IP probe failed for %s: %s", url, exc)
            continue

    cache.set(CACHE_KEY, "", 60)  # short cache for failures so we retry sooner
    return None
