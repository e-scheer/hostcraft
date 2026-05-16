from __future__ import annotations

from django.db import models


class NetworkProfile(models.Model):
    """Singleton holding the network exposure mode + custom domain.

    There's exactly one row (pk=1). Fetch with `NetworkProfile.current()`.
    """

    class Mode(models.TextChoices):
        DIRECT = "direct", "Direct (port-forward)"
        PLAYIT_GUIDED = "playit_guided", "Playit (guided)"
        PLAYIT_MANAGED = "playit_managed", "Playit (managed)"

    mode = models.CharField(max_length=32, choices=Mode.choices, default=Mode.DIRECT)
    custom_domain = models.CharField(max_length=255, blank=True, default="")
    # User-supplied hostname when mode == playit_guided (e.g. "abc.playit.gg").
    playit_hostname = models.CharField(max_length=255, blank=True, default="")
    # Encrypted at rest — only used when mode == playit_managed (Phase ulterior).
    playit_agent_key = models.TextField(blank=True, default="")
    # Manual override for the public IP (when ifconfig.me lies / behind weird NAT).
    public_ip_override = models.CharField(max_length=45, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "network_profile"

    @classmethod
    def current(cls) -> "NetworkProfile":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return f"NetworkProfile(mode={self.mode}, domain={self.custom_domain or '—'})"


class Allocation(models.Model):
    """Extra host:container port mapping for the MC container.

    The primary allocation (MC default port) lives in the compose file and
    isn't tracked here — it's surfaced read-only on the UI by reading the
    container's existing PortBindings.
    """

    class Protocol(models.TextChoices):
        TCP = "tcp", "TCP"
        UDP = "udp", "UDP"

    label = models.CharField(max_length=64)
    host_port = models.PositiveIntegerField()
    container_port = models.PositiveIntegerField()
    protocol = models.CharField(max_length=4, choices=Protocol.choices, default=Protocol.TCP)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "network_allocations"
        ordering = ["host_port"]
        constraints = [
            models.UniqueConstraint(
                fields=["host_port", "protocol"],
                name="uniq_alloc_host_port_proto",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} {self.host_port}/{self.protocol} → {self.container_port}"
