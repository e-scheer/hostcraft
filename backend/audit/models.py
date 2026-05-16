from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only log of mutating actions performed against the API.

    The user FK lets us attribute actions per-account once we go multi-user.
    Today there's only `admin`, but the schema is ready.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # Dotted path: "server.start", "files.delete", "backups.create".
    action = models.CharField(max_length=64, db_index=True)
    method = models.CharField(max_length=10, blank=True, default="")
    # Raw path or domain-specific identifier (e.g. file path, backup name).
    target = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    status_code = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.user_id} {self.action} {self.status}"
