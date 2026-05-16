"""Model that records mods/plugins installed via the marketplace.

We persist what we installed so we can offer Update and Uninstall, and so
we can show "X installed" badges in the search UI. The on-disk file is the
source of truth for whether something is *currently* present — this table
records *what we put there*. ``inventory.scan()`` reconciles the two.
"""

from __future__ import annotations

from django.db import models


class InstalledMod(models.Model):
    class Kind(models.TextChoices):
        MOD = "mod", "Mod"
        PLUGIN = "plugin", "Plugin"

    provider = models.CharField(max_length=32, db_index=True)        # 'modrinth' | 'hangar'
    project_id = models.CharField(max_length=128, db_index=True)
    project_slug = models.CharField(max_length=128, blank=True, default="")
    title = models.CharField(max_length=255)
    icon_url = models.URLField(blank=True, default="")
    project_url = models.URLField(blank=True, default="")

    version_id = models.CharField(max_length=128)
    version_number = models.CharField(max_length=64, blank=True, default="")
    filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=128, blank=True, default="")
    hash_algo = models.CharField(max_length=10, blank=True, default="")
    file_size = models.BigIntegerField(default=0)

    kind = models.CharField(max_length=10, choices=Kind.choices)
    loader = models.CharField(max_length=32, blank=True, default="")
    mc_version = models.CharField(max_length=32, blank=True, default="")

    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mods_installed"
        ordering = ["-installed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "project_id"],
                name="uniq_provider_project",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.project_slug or self.project_id} ({self.version_number})"
