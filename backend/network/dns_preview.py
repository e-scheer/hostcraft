"""Generate copy-pasteable DNS records for the user's registrar.

Output shape (consumed by the frontend `Allocations` / `Custom domain` cards):

    [
      {
        "type": "SRV",
        "name": "_minecraft._tcp.mc.example.com",
        "value": "0 5 25565 abc.playit.gg.",
        "ttl": 300,
        "comment": "Minecraft client follows SRV records natively …"
      },
      …
    ]
"""

from __future__ import annotations

from typing import Iterable

from .models import Allocation, NetworkProfile
from . import public_ip


def _ensure_dot(host: str) -> str:
    """DNS records expect FQDN ending with a dot."""
    return host if host.endswith(".") else host + "."


def build_records(
    profile: NetworkProfile,
    allocations: Iterable[Allocation],
    primary_port: int,
) -> list[dict]:
    """Compute the records the user should paste into their DNS zone."""
    records: list[dict] = []

    domain = (profile.custom_domain or "").strip().lower()
    if not domain:
        return records

    # Resolve the target hostname/IP based on the selected mode.
    target: str | None = None
    target_kind: str | None = None
    match profile.mode:
        case NetworkProfile.Mode.DIRECT:
            ip = (profile.public_ip_override or "").strip() or public_ip.detect()
            if ip:
                target = ip
                target_kind = "A"
        case NetworkProfile.Mode.PLAYIT_GUIDED | NetworkProfile.Mode.PLAYIT_MANAGED:
            host = (profile.playit_hostname or "").strip()
            if host:
                target = _ensure_dot(host)
                target_kind = "CNAME"

    if not target:
        return records

    # Apex / root mapping. For Playit (CNAME), this only works if the user
    # uses a subdomain (e.g. `mc.example.com`), not the apex. We don't try to
    # detect that here — the user knows what their domain is.
    if target_kind == "A":
        records.append({
            "type": "A",
            "name": domain,
            "value": target,
            "ttl": 300,
            "comment": "Direct A record for non-MC services (panel UI, web map).",
        })
    else:
        records.append({
            "type": "CNAME",
            "name": domain,
            "value": target,
            "ttl": 300,
            "comment": "CNAME alias to the Playit-assigned hostname.",
        })

    # Minecraft client follows SRV records natively, so we always emit one
    # for the MC port. This is what lets `mc.mondomaine.com` work without a
    # custom port suffix in the client.
    if target_kind == "A":
        srv_target = _ensure_dot(domain)
    else:
        srv_target = target  # already FQDN-with-dot

    records.append({
        "type": "SRV",
        "name": f"_minecraft._tcp.{domain}",
        "value": f"0 5 {primary_port} {srv_target}",
        "ttl": 300,
        "comment": "Minecraft client reads SRV first — this is what lets users connect with no port suffix.",
    })

    # Per-allocation hints — useful if the user wants a memorable subdomain
    # for, say, BlueMap (`map.example.com:8100` → CNAME to mc host).
    # Skip if direct A: the user can already use `<domain>:<port>`.
    if target_kind == "CNAME":
        for alloc in allocations:
            sub = alloc.label.lower().replace(" ", "-").replace("_", "-")
            sub = "".join(c for c in sub if c.isalnum() or c == "-").strip("-")
            if not sub:
                continue
            records.append({
                "type": "CNAME",
                "name": f"{sub}.{domain}",
                "value": target,
                "ttl": 300,
                "comment": (
                    f"Friendly alias for {alloc.label} "
                    f"(host port {alloc.host_port}/{alloc.protocol})."
                ),
            })

    return records
