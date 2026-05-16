from django.urls import path

from .views import (
    InstallView,
    InstalledView,
    ManualInspectView,
    ManualInstallView,
    SearchView,
    TargetView,
    UninstallView,
    VersionsView,
)

app_name = "mods"

urlpatterns = [
    path("target/", TargetView.as_view(), name="target"),
    path("search/", SearchView.as_view(), name="search"),
    path("versions/", VersionsView.as_view(), name="versions"),
    path("installed/", InstalledView.as_view(), name="installed"),
    path("install/", InstallView.as_view(), name="install"),
    path("upload/", ManualInstallView.as_view(), name="manual-install"),
    path("upload/inspect/", ManualInspectView.as_view(), name="manual-inspect"),
    path("<int:pk>/", UninstallView.as_view(), name="uninstall"),
]
