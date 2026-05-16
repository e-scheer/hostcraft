"""Singleton watchdog config — separate file so it doesn't tangle with the
PerfSample model that lives in `models.py` (different concern, same app)."""

from __future__ import annotations

from django.db import models


class WatchdogConfig(models.Model):
    """Auto-restart settings for the Minecraft container."""

    enabled = models.BooleanField(default=False)
    threshold_seconds = models.PositiveIntegerField(
        default=120,
        help_text="How long Health.Status must be `unhealthy` before we trigger a restart.",
    )
    max_restarts_per_hour = models.PositiveIntegerField(
        default=3,
        help_text="Hard cap to prevent boot-loops from hammering the host.",
    )
    last_restart_at = models.DateTimeField(null=True, blank=True)
    total_restarts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "server_watchdog"

    @classmethod
    def current(cls) -> "WatchdogConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return f"WatchdogConfig(enabled={self.enabled})"
