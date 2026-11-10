from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list_view, name="list"),
    path("trigger-daily/", views.trigger_daily_pipeline_view, name="trigger_daily"),
    path("<uuid:notification_id>/", views.notification_detail_view, name="detail"),
    path("<uuid:notification_id>/resend/", views.manual_resend_view, name="manual_resend"),
]
