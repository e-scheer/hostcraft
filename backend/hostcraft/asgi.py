"""ASGI entrypoint — supports HTTP + WebSocket via Channels."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hostcraft.settings")

# Initialize Django app registry first so models are loadable below.
django_asgi_app = get_asgi_application()

# Imports below intentionally come after get_asgi_application() — they need the
# app registry to be ready (custom user model, etc.).
from server.jwt_auth import JwtAuthMiddleware  # noqa: E402
from server.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
