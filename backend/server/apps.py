from django.apps import AppConfig


class ServerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "server"

    def ready(self) -> None:
        # Start background threads only in the actual web-serving process —
        # not in `manage.py migrate`, makemigrations, shell, etc.
        from .perf_collector import is_main_serving_process, start_collector
        from .watchdog import start_watchdog

        if is_main_serving_process():
            start_collector()
            start_watchdog()
