from django.urls import path
from . import views

app_name = "people"

urlpatterns = [
    path("", views.student_list_view, name="list"),
    path("add/", views.student_create_view, name="add"),
    path("export/csv/", views.export_students_csv, name="export_csv"),
    path("<uuid:student_id>/", views.student_detail_view, name="detail"),
    path("<uuid:student_id>/edit/", views.student_update_view, name="edit"),
    path("<uuid:student_id>/delete/", views.student_delete_view, name="delete"),
]
