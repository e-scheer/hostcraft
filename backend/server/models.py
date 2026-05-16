from __future__ import annotations

from django.db import models

# Re-export the watchdog model so Django sees it under this app's models module.
from .models_watchdog import WatchdogConfig  # noqa: F401


class PerfSample(models.Model):
    """One row per perf snapshot. Sampled by perf_collector every 30 s.

    NULL fields mean the source was unreachable at sampling time (e.g. RCON
    while booting, or Vanilla without the /tps command).
    """

    t = models.DateTimeField(auto_now_add=True, db_index=True)
    cpu_percent = models.FloatField(null=True)
    memory_used = models.BigIntegerField(null=True)
    memory_limit = models.BigIntegerField(null=True)
    players_online = models.IntegerField(null=True)
    players_max = models.IntegerField(null=True)
    tps_1m = models.FloatField(null=True)

    class Meta:
        db_table = "perf_samples"
        ordering = ["t"]
        indexes = [
            models.Index(fields=["-t"], name="perf_t_desc_idx"),
        ]
