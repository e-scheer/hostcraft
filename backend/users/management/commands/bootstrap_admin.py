"""Create the initial admin user on first boot, idempotently."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the initial admin user from HOSTCRAFT_INITIAL_ADMIN_* env vars (idempotent)."

    def handle(self, *_args, **_options) -> None:
        user_model = get_user_model()
        username = settings.INITIAL_ADMIN_USER
        password = settings.INITIAL_ADMIN_PASSWORD

        if not username or not password:
            self.stdout.write(self.style.WARNING("No INITIAL_ADMIN_* set, skipping."))
            return

        if user_model.objects.filter(username=username).exists():
            self.stdout.write(self.style.NOTICE(f"User {username!r} already exists, skipping."))
            return

        user_model.objects.create_superuser(username=username, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created admin user {username!r}."))
