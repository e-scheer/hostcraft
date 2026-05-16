from django.urls import path

from .views import (
    IconPresetRawView,
    IconPresetView,
    IconRawView,
    IconUploadView,
    IconView,
    OpsView,
    PropertiesView,
    RealtimeHistoryView,
    RealtimeView,
    WatchdogView,
    RestartView,
    RuntimeOptionsView,
    RuntimeView,
    StartView,
    StatusView,
    StopView,
    WhitelistView,
)

app_name = "server"

urlpatterns = [
    path("status/", StatusView.as_view(), name="status"),
    path("realtime/", RealtimeView.as_view(), name="realtime"),
    path("realtime/history/", RealtimeHistoryView.as_view(), name="realtime-history"),
    path("start/", StartView.as_view(), name="start"),
    path("stop/", StopView.as_view(), name="stop"),
    path("restart/", RestartView.as_view(), name="restart"),
    path("properties/", PropertiesView.as_view(), name="properties"),
    path("whitelist/", WhitelistView.as_view(), name="whitelist"),
    path("ops/", OpsView.as_view(), name="ops"),
    path("runtime/", RuntimeView.as_view(), name="runtime"),
    path("runtime/options/", RuntimeOptionsView.as_view(), name="runtime-options"),
    path("watchdog/", WatchdogView.as_view(), name="watchdog"),
    path("icon/", IconView.as_view(), name="icon"),
    path("icon/upload/", IconUploadView.as_view(), name="icon-upload"),
    path("icon/preset/", IconPresetView.as_view(), name="icon-preset"),
    path("icon/raw/", IconRawView.as_view(), name="icon-raw"),
    path(
        "icon/presets/<slug:preset_id>/raw/",
        IconPresetRawView.as_view(),
        name="icon-preset-raw",
    ),
]
