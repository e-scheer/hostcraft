"""Aggregated real-time snapshot for the Dashboard stat cards.

Single endpoint that gathers Docker stats + RCON list + RCON tps. Each source
fails independently — partial responses are normal (e.g. Vanilla has no /tps,
RCON unreachable while booting, etc.).
"""

from __future__ import annotations

import logging
import re

from . import docker_client, rcon

logger = logging.getLogger(__name__)


# Strip Minecraft section-sign color codes ("§a*20.0" → "*20.0")
_COLOR_RE = re.compile(r"§.")
_LIST_RE = re.compile(r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online")
_NUM_RE = re.compile(r"\d+\.?\d*")


def snapshot() -> dict:
    cpu_mem = docker_client.stats()
    list_resp, tps_resp = _rcon_pair("list", "tps")
    players = _parse_players(list_resp)
    tps = _parse_tps(tps_resp)
    return {
        **cpu_mem,
        "players_online": players[0] if players else None,
        "players_max": players[1] if players else None,
        "tps": tps,
    }


def _rcon_pair(*commands: str) -> tuple[str | None, ...]:
    """Run several RCON commands over a single connection.

    Returns a tuple aligned with ``commands``; an entry is ``None`` when
    RCON is unreachable or the call blew up. Aggregating both commands in
    one socket halves the per-poll connection churn the MC console used
    to log on every Dashboard tick.
    """
    try:
        results = rcon.send_many(list(commands))
    except rcon.RconUnavailable:
        return tuple(None for _ in commands)
    except Exception:  # noqa: BLE001
        logger.exception("rcon batch failed")
        return tuple(None for _ in commands)
    return tuple(results)


def _parse_players(resp: str | None) -> tuple[int, int] | None:
    if not resp:
        return None
    m = _LIST_RE.search(resp)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_tps(resp: str | None) -> list[float] | None:
    """Paper-only: parse `tps` command output. Returns None on Vanilla.

    Paper response shape:
      "§6TPS from last 1m, 5m, 15m: §a*20.0, §a*20.0, §a*20.0"
    We split on ":" and parse only the right-hand side so we don't pick up
    the "1m / 5m / 15m" labels by mistake.
    """
    if not resp:
        return None
    clean = _COLOR_RE.sub("", resp)
    if ":" not in clean:
        return None
    rhs = clean.rsplit(":", 1)[1]
    nums = _NUM_RE.findall(rhs)
    if len(nums) < 3:
        return None
    try:
        return [float(nums[0]), float(nums[1]), float(nums[2])]
    except ValueError:
        return None
