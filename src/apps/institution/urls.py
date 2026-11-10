from django.urls import path
from . import views

app_name = "institution"

urlpatterns = [
    path("", views.admin_panel_view, name="admin_panel"),
]
