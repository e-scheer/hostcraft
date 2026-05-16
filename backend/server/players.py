"""Helpers for the visual editors of whitelist.json and ops.json.

- Read & write the JSON files with proper file locking-style atomicity.
- Look up Mojang UUIDs from a username (so the user only has to type a name).
- Fire RCON commands when the server is running, so changes apply instantly
  without waiting for a restart.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.translation import gettext as _

from . import rcon

logger = logging.getLogger(__name__)


WHITELIST_FILE = "whitelist.json"
OPS_FILE = "ops.json"

DEFAULT_OP_LEVEL = 4
MIN_OP_LEVEL = 1
MAX_OP_LEVEL = 4


class PlayerLookupError(RuntimeError):
    """Raised when we couldn't resolve a Minecraft username to a UUID."""


# ---------------------------------------------------------------------------
# Mojang lookup
# ---------------------------------------------------------------------------


def lookup_username(name: str) -> tuple[str, str]:
    """Resolve `name` to (uuid_with_dashes, canonical_name).

    Hits api.mojang.com — keep it short-circuited and timed-out so a Mojang
    outage doesn't hang the panel.
    """
    name = (name or "").strip()
    if not name:
        raise PlayerLookupError(_("Player name is required."))

    url = f"https://api.mojang.com/users/profiles/minecraft/{name}"
    req = Request(url, headers={"User-Agent": "hostcraft-panel"})
    try:
        with urlopen(req, timeout=5) as resp:  # noqa: S310 — fixed Mojang URL
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404 or exc.code == 204:
            raise PlayerLookupError(
                _("Unknown Minecraft player: %(name)s") % {"name": name}
            ) from exc
        raise PlayerLookupError(
            _("Mojang lookup failed (%(code)s).") % {"code": exc.code}
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PlayerLookupError(_("Mojang lookup unreachable.")) from exc

    raw_id = data.get("id", "")
    canonical = data.get("name", name)
    if len(raw_id) != 32:
        raise PlayerLookupError(_("Mojang returned an unexpected response."))
    return _format_uuid(raw_id), canonical


def _format_uuid(raw: str) -> str:
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


def read_whitelist() -> list[dict]:
    return _read_json_list(_path(WHITELIST_FILE))


def add_whitelist(name: str) -> dict:
    uuid, canonical = lookup_username(name)
    entries = read_whitelist()
    if any(e.get("uuid") == uuid for e in entries):
        # Already there: refresh canonical name silently.
        for e in entries:
            if e.get("uuid") == uuid:
                e["name"] = canonical
        _write_json_list(_path(WHITELIST_FILE), entries)
        _try_rcon(f"whitelist reload")
        return {"uuid": uuid, "name": canonical}
    entry = {"uuid": uuid, "name": canonical}
    entries.append(entry)
    _write_json_list(_path(WHITELIST_FILE), entries)
    _try_rcon(f"whitelist add {canonical}")
    return entry


def remove_whitelist(uuid: str) -> bool:
    entries = read_whitelist()
    target = next((e for e in entries if e.get("uuid") == uuid), None)
    if target is None:
        return False
    entries = [e for e in entries if e.get("uuid") != uuid]
    _write_json_list(_path(WHITELIST_FILE), entries)
    _try_rcon(f"whitelist remove {target.get('name', '')}")
    return True


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


def read_ops() -> list[dict]:
    return _read_json_list(_path(OPS_FILE))


def add_op(name: str, level: int = DEFAULT_OP_LEVEL, bypasses_player_limit: bool = False) -> dict:
    # We DON'T send `/op` over RCON: vanilla Minecraft's /op forces level=4 and
    # rewrites ops.json after we do, blowing away custom levels and bypass.
    # ops.json is the source of truth; changes apply on the next server load.
    level = _clamp_level(level)
    uuid, canonical = lookup_username(name)
    entries = read_ops()
    found = next((e for e in entries if e.get("uuid") == uuid), None)
    if found is not None:
        found["name"] = canonical
        found["level"] = level
        found["bypassesPlayerLimit"] = bool(bypasses_player_limit)
        _write_json_list(_path(OPS_FILE), entries)
        return found

    entry = {
        "uuid": uuid,
        "name": canonical,
        "level": level,
        "bypassesPlayerLimit": bool(bypasses_player_limit),
    }
    entries.append(entry)
    _write_json_list(_path(OPS_FILE), entries)
    return entry


def update_op(uuid: str, *, level: int | None = None, bypasses_player_limit: bool | None = None) -> dict | None:
    entries = read_ops()
    target = next((e for e in entries if e.get("uuid") == uuid), None)
    if target is None:
        return None
    if level is not None:
        target["level"] = _clamp_level(level)
    if bypasses_player_limit is not None:
        target["bypassesPlayerLimit"] = bool(bypasses_player_limit)
    _write_json_list(_path(OPS_FILE), entries)
    return target


def remove_op(uuid: str) -> bool:
    # `/deop` over RCON works (it doesn't fight us on level/bypass), so we
    # send it for instant effect on the running server.
    entries = read_ops()
    target = next((e for e in entries if e.get("uuid") == uuid), None)
    if target is None:
        return False
    entries = [e for e in entries if e.get("uuid") != uuid]
    _write_json_list(_path(OPS_FILE), entries)
    _try_rcon(f"deop {target.get('name', '')}")
    return True


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _clamp_level(level: Any) -> int:
    try:
        n = int(level)
    except (TypeError, ValueError):
        n = DEFAULT_OP_LEVEL
    return max(MIN_OP_LEVEL, min(MAX_OP_LEVEL, n))


def _path(name: str) -> Path:
    return Path(settings.MC_DATA_PATH) / name


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_json_list(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish: write to .tmp then rename.
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(entries, fp, indent=2)
        fp.write("\n")
    tmp.replace(path)


def _try_rcon(command: str) -> None:
    """Best-effort: send a command via RCON; swallow when server is down."""
    try:
        rcon.send(command)
    except rcon.RconUnavailable as exc:
        logger.debug("RCON sync skipped (%s): %s", command, exc)
