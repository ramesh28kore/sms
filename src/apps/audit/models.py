"""
Audit models: append-only AuditEvent log.
Application roles cannot edit or delete normal audit history.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditEvent(models.Model):
    """
    Append-only application audit log.
    Covers: attendance changes, finalization, contact changes, imports,
    permissions, schedule/template changes, mode activation, dispatch attempts, manual resends.

    Security:
    - Phone numbers and message content are REDACTED from this table.
    - Sensitive diffs are stored only if the viewer has the reveal_contacts capability.
    - Application roles cannot UPDATE or DELETE these rows (enforced by DB permissions in production).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Actor (null for system/automated events)
    actor_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_description = models.CharField(
        _("actor description"), max_length=256, blank=True,
        help_text="Human-readable actor: 'System', worker ID, import job ID, etc.",
    )
    action = models.CharField(
        _("action"), max_length=128,
        help_text="Dot-notation action code e.g. 'attendance.finalize', 'user.login'.",
    )
    # Object references (use string IDs, not FK, to survive object deletion)
    object_type = models.CharField(_("object type"), max_length=128, blank=True)
    object_id = models.CharField(_("object ID"), max_length=64, blank=True)
    object_repr = models.CharField(
        _("object representation"), max_length=512, blank=True,
        help_text="Human-readable description of the object at the time of the event.",
    )
    # Diff/metadata (redacted: no phone numbers or message content)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)
    reason = models.TextField(_("reason"), blank=True)
    # Correlation
    correlation_id = models.CharField(_("correlation ID"), max_length=64, blank=True)
    request_path = models.CharField(_("request path"), max_length=512, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    recorded_at = models.DateTimeField(_("recorded at"), auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_event"
        verbose_name = _("audit event")
        verbose_name_plural = _("audit events")
        ordering = ["-recorded_at"]
        # Read-only in production: enforce via DB-level permissions or migration comment
        # Django ORM does not natively prevent updates; production setup should restrict.

    def __str__(self):
        return f"[{self.recorded_at}] {self.actor_description or self.actor_user} → {self.action}"

