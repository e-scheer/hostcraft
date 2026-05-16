from __future__ import annotations

from django.db import models


class Schedule(models.Model):
    class Kind(models.TextChoices):
        RESTART = "restart", "Restart server"
        BACKUP_WORLD = "backup_world", "Backup world"
        BACKUP_FULL = "backup_full", "Backup full"
        RCON = "rcon", "RCON command"

    class LastStatus(models.TextChoices):
        NEVER_RUN = "never_run", "Never run"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    cron = models.CharField(max_length=120, help_text="Standard 5-field cron")
    payload = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=20, choices=LastStatus.choices, default=LastStatus.NEVER_RUN
    )
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "schedules"
        ordering = ["-enabled", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind} @ {self.cron})"
