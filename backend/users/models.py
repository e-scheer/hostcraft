"""Custom user model.

Defined upfront (even if minimal today) because changing AUTH_USER_MODEL after
the first migration is a recurring Django pain point — better future-proof now
when Phase 1 adds TOTP secrets.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    totp_secret = models.CharField(max_length=64, blank=True, default="")

    class Meta(AbstractUser.Meta):
        db_table = "users"
