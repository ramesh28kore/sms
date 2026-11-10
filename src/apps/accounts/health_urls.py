"""Health check URL patterns (not part of main app namespace)."""
from django.urls import path

from .health_views import LivenessView, ReadinessView

urlpatterns = [
    path("live/", LivenessView.as_view(), name="health_live"),
    path("ready/", ReadinessView.as_view(), name="health_ready"),
]

