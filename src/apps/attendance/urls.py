from django.urls import path
from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.session_list_view, name="session_list"),
    path("session/<uuid:session_id>/", views.session_register_view, name="register"),
]
