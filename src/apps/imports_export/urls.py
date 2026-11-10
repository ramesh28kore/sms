from django.urls import path
from . import views

app_name = "imports_export"

urlpatterns = [
    path("upload/", views.import_upload_view, name="upload"),
    path("<uuid:job_id>/preview/", views.import_preview_view, name="preview"),
    path("<uuid:job_id>/commit/", views.import_commit_view, name="commit"),
]
