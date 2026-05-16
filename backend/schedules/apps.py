from __future__ import annotations

import os
import sys

from django.apps import AppConfig


def _is_main_serving_process() -> bool:
    """True only inside the actual HTTP-serving process.

    Avoids running the scheduler:
      - from `manage.py migrate` (it would touch DB before tables exist),
      - twice under runserver's autoreload (parent watcher + child),
      - during makemigrations/shell/collectstatic/compilemessages/etc.
    """
    argv0 = sys.argv[0] if sys.argv else ""
    if "daphne" in argv0 or "gunicorn" in argv0:
        return True
    if "manage.py" in argv0 and "runserver" in sys.argv:
        # runserver child reloader sets RUN_MAIN=true
        return os.environ.get("RUN_MAIN") == "true"
    return False


class SchedulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "schedules"

    def ready(self) -> None:
        if os.environ.get("HOSTCRAFT_DISABLE_SCHEDULER") == "1":
            return
        if not _is_main_serving_process():
            return
        # Local import — defer until Django apps are fully loaded.
        from . import scheduler
        scheduler.start()
