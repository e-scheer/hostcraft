from django.urls import path

from .views import (
    AllocationDetailView,
    AllocationListCreateView,
    PlayitAgentLogsView,
    PlayitAgentRefreshView,
    PlayitAgentView,
    ProfileView,
    RefreshPublicIpView,
)

app_name = "network"

urlpatterns = [
    path("", ProfileView.as_view(), name="profile"),
    path("allocations/", AllocationListCreateView.as_view(), name="allocations"),
    path("allocations/<int:pk>/", AllocationDetailView.as_view(), name="allocation-detail"),
    path("refresh-ip/", RefreshPublicIpView.as_view(), name="refresh-ip"),
    path("playit/agent/", PlayitAgentView.as_view(), name="playit-agent"),
    path("playit/agent/logs/", PlayitAgentLogsView.as_view(), name="playit-agent-logs"),
    path(
        "playit/agent/refresh/",
        PlayitAgentRefreshView.as_view(),
        name="playit-agent-refresh",
    ),
]
