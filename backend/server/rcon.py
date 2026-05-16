"""Minimal Source RCON client (Valve protocol).

Implemented in stdlib because mcrcon uses signal.alarm for its timeout, which
breaks anywhere outside the main thread (e.g. Channels' threadpool).

Protocol reference: https://developer.valvesoftware.com/wiki/Source_RCON_Protocol
"""

from __future__ import annotations

import logging
import socket
import struct
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_PACKET_AUTH = 3
_PACKET_AUTH_RESP = 2
_PACKET_CMD = 2
_PACKET_RESP = 0


class RconUnavailable(RuntimeError):
    """RCON misconfigured, unreachable, or auth failed."""


# ---------------------------------------------------------------------------
# Persistent connection
#
# Without this, every realtime poll (Dashboard, perf collector) opens a fresh
# RCON socket, which Paper logs as "Thread RCON Client started/shutting down".
# Reusing one authenticated socket across calls keeps the MC console quiet
# and saves the auth + TCP handshake every few seconds.
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_sock: socket.socket | None = None
_req_id: int = 1


def _close_sock() -> None:
    global _sock
    if _sock is not None:
        try:
            _sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            _sock.close()
        except OSError:
            pass
    _sock = None


def _connect(timeout: float) -> socket.socket:
    global _sock, _req_id
    if not settings.MC_RCON_PASSWORD:
        raise RconUnavailable("RCON password not configured")
    try:
        sock = socket.create_connection(
            (settings.MC_RCON_HOST, settings.MC_RCON_PORT),
            timeout=timeout,
        )
        sock.settimeout(timeout)
        _write(sock, 1, _PACKET_AUTH, settings.MC_RCON_PASSWORD)
        rid, _rtype, _body = _read(sock)
        if rid == -1:
            sock.close()
            raise RconUnavailable("RCON authentication failed")
    except (OSError, ConnectionError) as exc:
        raise RconUnavailable(f"RCON unreachable: {exc}") from exc
    _sock = sock
    _req_id = 2
    return sock


def _send_via(sock: socket.socket, commands: list[str]) -> list[str]:
    """Send commands on an already-authed socket. Caller holds the lock."""
    global _req_id
    results: list[str] = []
    for cmd in commands:
        _write(sock, _req_id, _PACKET_CMD, cmd)
        _, _, body = _read(sock)
        _req_id = (_req_id + 1) & 0x7FFFFFFF
        results.append(body)
    return results


def send(command: str, timeout: float = 5.0) -> str:
    return send_many([command], timeout=timeout)[0]


def send_many(commands: list[str], timeout: float = 5.0) -> list[str]:
    """Run several RCON commands over the persistent connection.

    Reuses the cached authed socket; on the first network/EOF error the
    connection is dropped + reopened transparently, then the commands are
    retried once. Multiple callers serialize on a module lock — RCON
    commands are fast (sub-ms typical), so this is fine for our load.
    """
    if not commands:
        return []
    if not settings.MC_RCON_PASSWORD:
        raise RconUnavailable("RCON password not configured")

    with _lock:
        for attempt in (0, 1):
            sock = _sock or _connect(timeout)
            try:
                sock.settimeout(timeout)
                return _send_via(sock, commands)
            except (OSError, ConnectionError, RconUnavailable) as exc:
                _close_sock()
                if attempt == 1:
                    raise RconUnavailable(f"RCON unreachable: {exc}") from exc
                # First failure: drop the cached socket and try fresh.
                logger.debug("RCON reconnect after error: %s", exc)
                continue
        # Unreachable, satisfies type checkers.
        return []


def reset() -> None:
    """Forcibly drop the cached connection (e.g. after server restart)."""
    with _lock:
        _close_sock()


def _write(sock: socket.socket, req_id: int, req_type: int, payload: str) -> None:
    body = payload.encode("utf-8") + b"\x00\x00"
    packet = struct.pack("<ii", req_id, req_type) + body
    sock.sendall(struct.pack("<i", len(packet)) + packet)


def _read(sock: socket.socket) -> tuple[int, int, str]:
    length_bytes = _read_n(sock, 4)
    length = struct.unpack("<i", length_bytes)[0]
    if length < 10 or length > 4_096:
        raise RconUnavailable(f"RCON packet length out of range: {length}")
    payload = _read_n(sock, length)
    req_id, req_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2].decode("utf-8", errors="replace")
    return req_id, req_type, body


def _read_n(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RconUnavailable("RCON connection closed prematurely")
        buf.extend(chunk)
    return bytes(buf)
