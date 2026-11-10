"""
Audit service: record_event() — called from across the application.
Never raises; audit failure must not break core operations.
"""
import logging
from typing import Any, Optional

from django.http import HttpRequest

logger = logging.getLogger(__name__)


def record_event(
    action: str,
    actor=None,
    target_object=None,
    metadata: dict | None = None,
    reason: str = "",
    request: HttpRequest | None = None,
    correlation_id: str = "",
):
    """
    Record one audit event.
    Phone numbers, message text, and API keys must NOT be passed here.
    """
    try:
        from apps.audit.models import AuditEvent

        actor_user = None
        actor_description = "System"

        if actor is not None:
            try:
                from apps.accounts.models import User
                if isinstance(actor, User):
                    actor_user = actor
                    actor_description = str(actor)
            except Exception:
                actor_description = str(actor)

        object_type = ""
        object_id = ""
        object_repr = ""
        if target_object is not None:
            object_type = type(target_object).__name__
            try:
                object_id = str(target_object.pk)
            except Exception:
                pass
            try:
                object_repr = str(target_object)[:512]
            except Exception:
                pass

        ip_address = None
        request_path = ""
        if request:
            request_path = getattr(request, "path", "")[:512]
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")

        AuditEvent.objects.create(
            actor_user=actor_user,
            actor_description=actor_description,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            metadata=metadata or {},
            reason=reason,
            correlation_id=correlation_id,
            request_path=request_path,
            ip_address=ip_address,
        )
    except Exception as exc:
        # Audit failure must NEVER break the calling operation
        logger.error("Audit event recording failed for action '%s': %s", action, exc)

