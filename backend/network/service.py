"""Sync user-managed allocations to the running MC container.

Allocations live in our DB; PortBindings live on the Docker container. After
any change to allocations, this module rebuilds the PortBindings dict and
asks `server.runtime.apply_overrides` to recreate the container with them.
"""

from __future__ import annotations

import logging

from server import runtime as runtime_helpers

from .models import Allocation

logger = logging.getLogger(__name__)


def build_port_bindings() -> dict[str, list[dict[str, str]]]:
    """Build the Docker PortBindings dict from the Allocation table."""
    out: dict[str, list[dict[str, str]]] = {}
    for alloc in Allocation.objects.all():
        key = f"{alloc.container_port}/{alloc.protocol}"
        out[key] = [{"HostIp": "", "HostPort": str(alloc.host_port)}]
    return out


def sync_to_container() -> None:
    """Force a container recreate with the current allocations applied.

    Idempotent — recreating with identical bindings is a no-op for the user
    other than the brief restart. Caller should warn the user beforehand.
    """
    bindings = build_port_bindings()
    runtime_helpers.apply_overrides(extra_port_bindings=bindings, force=True)
