from django.urls import path

from .views import (
    BackupDetailView,
    BackupDownloadView,
    BackupListCreateView,
    BackupRestoreView,
    BackupSizesView,
    BackupUploadView,
    DestinationDetailView,
    DestinationListCreateView,
    DestinationTestView,
)

app_name = "backups"

urlpatterns = [
    path("", BackupListCreateView.as_view(), name="list"),
    path("sizes/", BackupSizesView.as_view(), name="sizes"),
    path("destinations/", DestinationListCreateView.as_view(), name="destinations"),
    path("destinations/<int:pk>/", DestinationDetailView.as_view(), name="destination-detail"),
    path("destinations/<int:pk>/test/", DestinationTestView.as_view(), name="destination-test"),
    path("<int:pk>/", BackupDetailView.as_view(), name="detail"),
    path("<int:pk>/download/", BackupDownloadView.as_view(), name="download"),
    path("<int:pk>/upload/", BackupUploadView.as_view(), name="upload"),
    path("<int:pk>/restore/", BackupRestoreView.as_view(), name="restore"),
]
