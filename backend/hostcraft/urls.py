"""Top-level URL configuration."""

from django.contrib import admin
from django.urls import include, path, re_path

from hostcraft.views import SpaView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("users.urls")),
    path("api/server/", include("server.urls")),
    path("api/files/", include("files.urls")),
    path("api/backups/", include("backups.urls")),
    path("api/schedules/", include("schedules.urls")),
    path("api/audit/", include("audit.urls")),
    path("api/network/", include("network.urls")),
    path("api/mods/", include("mods.urls")),
    path("api/worldmap/", include("worldmap.urls")),
    path("api/", include("api.urls")),
    # SPA fallback — every non-/api, non-/admin, non-/static path returns the SPA.
    re_path(r"^(?!api/|admin/|static/).*$", SpaView.as_view(), name="spa"),
]
