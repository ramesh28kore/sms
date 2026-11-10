"""URL patterns for accounts app."""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.root_redirect_view, name="root"),
    path("profile/", views.profile_view, name="profile"),
]

