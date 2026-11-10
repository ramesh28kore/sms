from django.urls import path
from . import views

app_name = "people"

urlpatterns = [
    path("", views.student_list_view, name="list"),
    path("<uuid:student_id>/", views.student_detail_view, name="detail"),
    path("export/csv/", views.export_students_csv, name="export_csv"),
]
