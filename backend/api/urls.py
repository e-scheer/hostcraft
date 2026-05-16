from django.urls import path

from .views import HealthView, VersionView

app_name = "api"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("version/", VersionView.as_view(), name="version"),
]
