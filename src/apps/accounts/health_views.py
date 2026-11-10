"""Liveness and readiness health check endpoints."""
import json

from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views import View


class LivenessView(View):
    """
    Liveness probe: returns 200 if the process is alive.
    Does NOT send SMS or perform expensive checks.
    Detail is available only to authenticated staff (see readiness).
    """
    def get(self, request):
        return HttpResponse("ok", content_type="text/plain", status=200)


class ReadinessView(View):
    """
    Readiness probe: checks DB connectivity.
    Returns 200 if ready, 503 if not.
    Sanitized output — no stack traces or config details.
    """
    def get(self, request):
        checks = {}
        overall = True
        try:
            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            overall = False

        status = 200 if overall else 503
        return JsonResponse({"status": "ok" if overall else "unavailable", "checks": checks}, status=status)

