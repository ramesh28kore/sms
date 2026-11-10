"""Root URL configuration for Avanthi Attendance & Parent Alerts."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import LockedOutView
from apps.reporting.views import (
    attendance_report,
    attendance_report_export,
    attendance_report_session_detail,
    attendance_report_sessions,
)

# Restrict Django admin to a non-default path; set ADMIN_URL in env for production.
ADMIN_URL = getattr(settings, "ADMIN_URL", "django-admin/")

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("accounts/locked/", LockedOutView.as_view(), name="account_locked"),
    path("", include("apps.accounts.urls", namespace="accounts")),
    path("dashboard/", include("apps.reporting.urls", namespace="reporting")),
    path("reports/", attendance_report, name="attendance_report"),
    path("reports/sessions/", attendance_report_sessions, name="attendance_report_sessions"),
    path(
        "reports/sessions/<uuid:session_id>/",
        attendance_report_session_detail,
        name="attendance_report_session_detail",
    ),
    path("reports/export/", attendance_report_export, name="attendance_report_export"),
    path("students/", include("apps.people.urls", namespace="people")),
    path("attendance/", include("apps.attendance.urls", namespace="attendance")),
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("admin-panel/", include("apps.institution.urls", namespace="institution")),
    path("academics/", include("apps.academics.urls", namespace="academics")),
    path("scheduling/", include("apps.scheduling.urls", namespace="scheduling")),
    path("gateways/", include("apps.gateways.urls", namespace="gateways")),
    path("imports/", include("apps.imports_export.urls", namespace="imports_export")),
    path("audit/", include("apps.audit.urls", namespace="audit")),
    path("health/", include("apps.accounts.health_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
