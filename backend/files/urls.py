from django.urls import path

from .views import (
    DeleteView,
    DownloadView,
    ListView,
    MkdirView,
    MoveView,
    ReadView,
    UploadView,
    WriteView,
)

app_name = "files"

urlpatterns = [
    path("", ListView.as_view(), name="list"),
    path("read/", ReadView.as_view(), name="read"),
    path("write/", WriteView.as_view(), name="write"),
    path("download/", DownloadView.as_view(), name="download"),
    path("upload/", UploadView.as_view(), name="upload"),
    path("mkdir/", MkdirView.as_view(), name="mkdir"),
    path("delete/", DeleteView.as_view(), name="delete"),
    path("move/", MoveView.as_view(), name="move"),
]
