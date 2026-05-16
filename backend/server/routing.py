from django.urls import path

from .consumers import ConsoleConsumer

websocket_urlpatterns = [
    path("ws/console/", ConsoleConsumer.as_asgi()),
]
