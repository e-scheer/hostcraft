from __future__ import annotations

from django.db import models


class BackupDestination(models.Model):
    """A remote S3-compatible bucket where backups are pushed."""

    class Kind(models.TextChoices):
        S3 = "s3", "S3-compatible"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.S3)
    endpoint_url = models.CharField(
        max_length=255, blank=True, default="",
        help_text="e.g. https://s3.us-west-001.backblazeb2.com — leave blank for AWS S3",
    )
    bucket = models.CharField(max_length=255)
    prefix = models.CharField(max_length=255, blank=True, default="")
    region = models.CharField(max_length=64, blank=True, default="us-east-1")
    # Credentials are stored in plaintext inside the panel-data SQLite DB.
    # The DB file lives in a Docker named volume the panel container alone can
    # touch. If you expose this DB to other tenants, encrypt it at rest.
    access_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    auto_upload = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backup_destinations"
        ordering = ["-enabled", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}/{self.bucket})"


class Backup(models.Model):
    class Kind(models.TextChoices):
        WORLD = "world", "World"
        FULL = "full", "Full data"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class RemoteStatus(models.TextChoices):
        NONE = "none", "Local only"
        PENDING = "pending", "Pending upload"
        UPLOADING = "uploading", "Uploading"
        UPLOADED = "uploaded", "Uploaded"
        FAILED = "failed", "Upload failed"

    class RestoreStatus(models.TextChoices):
        IDLE = "idle", "Idle"
        RUNNING = "running", "Restoring"
        DONE = "done", "Restored"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=200)
    path = models.CharField(max_length=512, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.WORLD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Off-site sync state (Phase 1.6b).
    remote_status = models.CharField(
        max_length=20, choices=RemoteStatus.choices, default=RemoteStatus.NONE
    )
    remote_destination = models.ForeignKey(
        BackupDestination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backups",
    )
    remote_key = models.CharField(max_length=512, blank=True, default="")
    remote_error = models.TextField(blank=True, default="")

    # Restore state — set on the backup that's currently being applied. Idle
    # for everything else.
    restore_status = models.CharField(
        max_length=20, choices=RestoreStatus.choices, default=RestoreStatus.IDLE
    )
    restore_error = models.TextField(blank=True, default="")
    restored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "backups"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}, {self.status})"
