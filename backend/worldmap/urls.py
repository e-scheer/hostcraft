from django.urls import path

from .views import WorldmapInstallView, WorldmapStatusView

app_name = "worldmap"

urlpatterns = [
    path("", WorldmapStatusView.as_view(), name="status"),
    path("install/", WorldmapInstallView.as_view(), name="install"),
]
