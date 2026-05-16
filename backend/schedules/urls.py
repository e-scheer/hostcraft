from django.urls import path

from .views import ScheduleDetailView, ScheduleListCreateView, ScheduleRunNowView

app_name = "schedules"

urlpatterns = [
    path("", ScheduleListCreateView.as_view(), name="list"),
    path("<int:pk>/", ScheduleDetailView.as_view(), name="detail"),
    path("<int:pk>/run/", ScheduleRunNowView.as_view(), name="run"),
]
