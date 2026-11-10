"""
Notifications models:
NotificationPolicyVersion, MessageTemplateVersion,
DailyNotificationIntent, RecipientSlot, Notification,
NotificationPayloadVersion, DeliveryAttempt, ManualSendAuthorization,
DestinationDispatchGuard, OutboxEvent, DispatchControl.

Design (from NOTIFICATION_DESIGN.md):
- One intent per student/date/kind. Database uniqueness enforced.
- Recipients are frozen when first queued; phone changes cancel, not retarget.
- stat=true = dispatch accepted (NOT delivery). stat=false = NOT success.
- UNKNOWN_OUTCOME never auto-retries.
- Attempt is persisted BEFORE the HTTP call.
- PostgreSQL owns all notification state; Redis is just a wake-up transport.
"""
import uuid
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _


class AbsenceRuleChoices(models.TextChoices):
    FULL_DAY_ABSENT = "full_day_absent", _("Full Day Absent (all held sessions absent)")
    ANY_SESSION_ABSENT = "any_session_absent", _("Any Session Absent")
    THRESHOLD = "threshold", _("Absent Session Threshold")


class NotificationPolicyVersion(models.Model):
    """
    Versioned notification policy. Immutable after first use.
    Distinct from academic attendance policy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("code"), max_length=64, unique=True)
    absence_rule = models.CharField(
        _("absence rule"), max_length=32, choices=AbsenceRuleChoices.choices,
        default=AbsenceRuleChoices.FULL_DAY_ABSENT,
    )
    # For THRESHOLD rule
    absent_session_threshold = models.PositiveSmallIntegerField(
        _("absent session threshold"), null=True, blank=True,
        help_text="Minimum absent sessions to trigger notification. For THRESHOLD rule only.",
    )
    # Excuse treatment
    excused_counts_as_absent = models.BooleanField(
        _("excused counts as absent"), default=False,
        help_text="For FULL_DAY rule: if True, EXCUSED does not exclude the student.",
    )
    # Recipient policy
    notify_all_designated = models.BooleanField(
        _("notify all designated recipients"), default=False,
        help_text="If True, notify all designated guardians. If False, notify primary only.",
    )
    # Time window (stored as strings; converted to UTC per sending date)
    notification_time = models.TimeField(
        _("notification time"),
        help_text="Earliest local time to send daily notifications (after final period).",
    )
    latest_send_time = models.TimeField(
        _("latest send time"),
        help_text="Sending window closes at this local time. Work after this is expired.",
    )
    is_active = models.BooleanField(_("active"), default=True)
    effective_from = models.DateField(_("effective from"))
    effective_until = models.DateField(_("effective until"), null=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    configured_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_policy_version"
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.code} ({self.get_absence_rule_display()}) from {self.effective_from}"


class MessageTemplateVersion(models.Model):
    """
    Versioned SMS message template. Immutable after use.
    Allowlisted placeholders only; no general template evaluation.
    Partial-day rule cannot select full-day template.
    """
    PLACEHOLDER_ALLOWLIST = [
        "student_name", "hall_ticket_number", "branch_code", "study_year",
        "semester", "section", "attendance_date", "absent_sessions",
        "held_sessions", "institute_name", "approved_short_name",
        "institute_contact",
    ]

    class LanguageChoices(models.TextChoices):
        ENGLISH = "en", _("English")
        TELUGU = "te", _("Telugu")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("template code"), max_length=64)
    version_number = models.PositiveIntegerField(_("version"), default=1)
    language = models.CharField(
        _("language"), max_length=8, choices=LanguageChoices.choices,
        default=LanguageChoices.ENGLISH,
    )
    # Compatible absence rule (partial-day template must not be used for full-day)
    compatible_rule = models.CharField(
        _("compatible rule"), max_length=32, choices=AbsenceRuleChoices.choices,
        default=AbsenceRuleChoices.FULL_DAY_ABSENT,
    )
    template_text = models.TextField(
        _("template text"),
        default=(
            "Dear Parent, {student_name} ({hall_ticket_number}), {branch_code} "
            "Year {study_year}, was marked absent for all held classes on "
            "{attendance_date}. Contact {institute_contact} if incorrect. "
            "- {approved_short_name}"
        ),
    )
    # Estimated segment count (computed on save; labeled as estimate)
    estimated_segments = models.PositiveSmallIntegerField(_("estimated segments"), default=1)
    is_unicode = models.BooleanField(_("uses Unicode / non-GSM-7"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    is_approved = models.BooleanField(
        _("approved for use"), default=False,
        help_text="Telugu and new templates must be approved before live activation.",
    )
    approval_note = models.TextField(_("approval note"), blank=True)
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_templates",
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="templates_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_template_version"
        unique_together = [("code", "version_number", "language")]
        ordering = ["-version_number"]

    def __str__(self):
        return f"{self.code} v{self.version_number} [{self.language}]"


class NotificationKindChoices(models.TextChoices):
    DAILY_ABSENCE = "daily_absence", _("Daily Absence Alert")


class NotificationStatusChoices(models.TextChoices):
    BLOCKED = "blocked", _("Blocked")
    QUEUED = "queued", _("Queued")
    DISPATCHING = "dispatching", _("Dispatching")
    DISPATCH_ACCEPTED = "dispatch_accepted", _("Dispatch Accepted")
    FAILED = "failed", _("Failed")
    UNKNOWN_OUTCOME = "unknown_outcome", _("Unknown Outcome")
    CANCELLED = "cancelled", _("Cancelled")
    EXPIRED = "expired", _("Expired")


class DailyNotificationIntent(models.Model):
    """
    One business intent per student/date/kind.
    Stable identity — template, policy, phone, schedule changes do NOT create a new intent.
    Database unique constraint enforces this.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Namespace: 'live' or a simulation run ID string
    namespace = models.CharField(_("namespace"), max_length=64, default="live")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="notification_intents")
    attendance_date = models.DateField(_("attendance date"))
    kind = models.CharField(
        _("kind"), max_length=32, choices=NotificationKindChoices.choices,
        default=NotificationKindChoices.DAILY_ABSENCE,
    )
    policy_version = models.ForeignKey(
        NotificationPolicyVersion, on_delete=models.PROTECT, related_name="intents", null=True, blank=True
    )
    # Plan/summary revision at intent creation
    plan_revision = models.PositiveIntegerField(_("plan revision"), default=1)
    # Recipients are frozen when first queued
    recipients_frozen = models.BooleanField(_("recipients frozen"), default=False)
    recipients_frozen_at = models.DateTimeField(_("recipients frozen at"), null=True, blank=True)
    # Aggregate status
    intent_status = models.CharField(
        _("intent status"), max_length=32, choices=NotificationStatusChoices.choices,
        default=NotificationStatusChoices.BLOCKED,
    )
    # Blocking reason when BLOCKED
    block_reason = models.CharField(_("block reason"), max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_daily_intent"
        unique_together = [("namespace", "student", "attendance_date", "kind")]
        ordering = ["-attendance_date"]

    def __str__(self):
        return f"Intent [{self.kind}] {self.student} on {self.attendance_date} [{self.intent_status}]"


class RecipientSlot(models.Model):
    """
    One slot in the frozen recipient plan for an intent.
    Stable slot ID; identifies a specific student–guardian–contact combination.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(DailyNotificationIntent, on_delete=models.PROTECT, related_name="recipient_slots")
    stable_slot_key = models.CharField(_("stable slot key"), max_length=128)
    # Frozen references (may differ from current after edits)
    guardian_id_snapshot = models.UUIDField(_("guardian ID snapshot"), null=True, blank=True)
    link_id_snapshot = models.UUIDField(_("link ID snapshot"), null=True, blank=True)
    contact_id_snapshot = models.UUIDField(_("contact ID snapshot"), null=True, blank=True)
    # Frozen normalized destination (E.164)
    frozen_destination = models.CharField(
        _("frozen destination"), max_length=20,
        help_text="Normalized E.164 at the time of recipient plan freeze. Immutable.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_recipient_slot"
        unique_together = [("intent", "stable_slot_key"), ("intent", "frozen_destination")]

    def __str__(self):
        return f"Slot {self.stable_slot_key} → {self.frozen_destination}"


class Notification(models.Model):
    """
    One notification record per intent/recipient slot.
    unique_together on intent + frozen destination prevents duplicate automatic sends.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(DailyNotificationIntent, on_delete=models.PROTECT, related_name="notifications")
    recipient_slot = models.ForeignKey(RecipientSlot, on_delete=models.PROTECT, related_name="notifications")
    status = models.CharField(
        _("status"), max_length=32, choices=NotificationStatusChoices.choices,
        default=NotificationStatusChoices.BLOCKED,
    )
    block_reason = models.CharField(_("block reason"), max_length=512, blank=True)
    is_simulation = models.BooleanField(_("simulation"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_notification"
        unique_together = [
            ("intent", "recipient_slot"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification {self.id} [{self.status}]"


class NotificationPayloadVersion(models.Model):
    """
    Immutable rendered message for one delivery attempt.
    Historical evidence is never replaced by current profile data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name="payload_versions"
    )
    rendered_text = models.TextField(_("rendered text"))
    destination = models.CharField(_("destination"), max_length=20)
    source_template_version = models.ForeignKey(
        MessageTemplateVersion, on_delete=models.PROTECT, related_name="payload_versions",
        null=True, blank=True,
    )
    source_policy_version = models.ForeignKey(
        NotificationPolicyVersion, on_delete=models.PROTECT, related_name="payload_versions",
        null=True, blank=True,
    )
    language = models.CharField(_("language"), max_length=8, default="en")
    estimated_segments = models.PositiveSmallIntegerField(default=1)
    estimator_version = models.CharField(_("estimator version"), max_length=16, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_payload_version"
        ordering = ["-created_at"]


class DeliveryAttemptPhaseChoices(models.TextChoices):
    BEFORE_REQUEST = "before_request", _("Before HTTP request")
    DURING_REQUEST = "during_request", _("During HTTP request")
    AFTER_RESPONSE = "after_response", _("After HTTP response")


class DeliveryAttemptOutcomeChoices(models.TextChoices):
    PENDING = "pending", _("Pending")
    DISPATCH_ACCEPTED = "dispatch_accepted", _("Dispatch accepted (stat=true)")
    FAILED_PRE_SUBMIT = "failed_pre_submit", _("Failed before submission")
    FAILED_POST_SUBMIT = "failed_post_submit", _("Failed after possible submission")
    UNKNOWN_OUTCOME = "unknown_outcome", _("Unknown outcome (may have submitted)")
    CANCELLED = "cancelled", _("Cancelled")


class DeliveryAttempt(models.Model):
    """
    One HTTP attempt to the gateway. Persisted BEFORE the HTTP call.
    HTTP 200 alone is NOT success; stat=true in body = dispatch accepted.
    stat=false = NOT success. Ambiguous outcomes = UNKNOWN_OUTCOME (no auto-retry).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, null=True, blank=True, on_delete=models.PROTECT, related_name="delivery_attempts"
    )
    manual_authorization = models.ForeignKey(
        "ManualSendAuthorization", null=True, blank=True,
        on_delete=models.PROTECT, related_name="delivery_attempts",
    )
    attempt_number = models.PositiveSmallIntegerField(_("attempt number"), default=1)
    # For automatic attempts: must match current institute dispatcher generation
    dispatcher_generation = models.PositiveIntegerField(_("dispatcher generation"), default=0)
    is_simulation = models.BooleanField(_("simulation"), default=True)
    gateway = models.ForeignKey(
        "gateways.GatewayConfig", null=True, blank=True,
        on_delete=models.PROTECT, related_name="delivery_attempts",
    )
    payload_version = models.ForeignKey(
        NotificationPayloadVersion, null=True, blank=True,
        on_delete=models.PROTECT, related_name="delivery_attempts",
    )
    phase = models.CharField(
        _("phase"), max_length=32, choices=DeliveryAttemptPhaseChoices.choices,
        default=DeliveryAttemptPhaseChoices.BEFORE_REQUEST,
    )
    outcome = models.CharField(
        _("outcome"), max_length=32, choices=DeliveryAttemptOutcomeChoices.choices,
        default=DeliveryAttemptOutcomeChoices.PENDING,
    )
    error_message = models.TextField(_("error message"), blank=True)
    # HTTP evidence (sanitized — no phone/message content in this field)
    http_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    gateway_stat_value = models.BooleanField(
        _("gateway stat value"), null=True, blank=True,
        help_text="Value of 'stat' field in gateway response. null = no parseable response.",
    )
    # Timing
    attempt_started_at = models.DateTimeField(_("attempt started"), null=True, blank=True)
    attempt_ended_at = models.DateTimeField(_("attempt ended"), null=True, blank=True)
    # Worker claim for crash recovery
    worker_id = models.CharField(_("worker ID"), max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(_("lease expires"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_delivery_attempt"
        ordering = ["-created_at"]
        # Only one active (PENDING/DISPATCHING) attempt per notification
        # Enforced by conditional unique index in migration.

    def __str__(self):
        return f"Attempt #{self.attempt_number} → {self.outcome}"


class ManualSendAuthorization(models.Model):
    """
    Explicit one-use authorization for a manual or test send.
    Cannot be reused; each physical attempt needs its own authorization.
    Linked to original intent for absence resends.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_token = models.CharField(_("action token"), max_length=128, unique=True)
    purpose = models.CharField(
        _("purpose"), max_length=64,
        help_text="e.g., 'manual_resend', 'test_message', 'correction'.",
    )
    student = models.ForeignKey(
        "people.Student", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    original_intent = models.ForeignKey(
        DailyNotificationIntent, null=True, blank=True,
        on_delete=models.PROTECT, related_name="manual_authorizations",
    )
    # Exact destination and message text (immutable after creation)
    destination = models.CharField(_("destination"), max_length=20)
    message_text = models.TextField(_("message text"))
    estimated_segments = models.PositiveSmallIntegerField(default=1)
    # Preview hash to bind authorization to payload
    preview_hash = models.CharField(_("preview hash"), max_length=64)
    reason = models.TextField(_("reason"))
    authorized_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="manual_authorizations"
    )
    authorized_at = models.DateTimeField(auto_now_add=True)
    mfa_verified_at = models.DateTimeField(_("MFA verified at"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"))
    is_used = models.BooleanField(_("used"), default=False)
    duplicate_risk_acknowledged = models.BooleanField(
        _("duplicate risk acknowledged"), default=False
    )
    is_simulation = models.BooleanField(_("simulation"), default=True)

    class Meta:
        db_table = "notifications_manual_authorization"

    def __str__(self):
        return f"ManualAuth [{self.purpose}] by {self.authorized_by}"


class DestinationDispatchGuard(models.Model):
    """
    Per-destination lock preventing duplicate automatic sends.
    Covers student/date/disclosure_family/destination.
    Automatic + manual absence resends share the ABSENCE disclosure family.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(_("namespace"), max_length=64, default="live")
    student = models.ForeignKey(
        "people.Student", null=True, blank=True, on_delete=models.PROTECT, related_name="dispatch_guards"
    )
    attendance_date = models.DateField(_("attendance date"), null=True, blank=True)
    disclosure_family = models.CharField(
        _("disclosure family"), max_length=64, default="absence",
        help_text="Groups automatic, correction, and manual resend for the same event.",
    )
    destination_key = models.CharField(
        _("destination key"), max_length=20,
        help_text="Normalized E.164 destination.",
    )
    # State
    is_active = models.BooleanField(_("active"), default=True)
    has_possible_submission = models.BooleanField(
        _("has possible submission"), default=False,
        help_text="True after any possibly-submitted attempt. Manual resend requires explicit acknowledgement.",
    )
    locked_notification = models.ForeignKey(
        Notification, null=True, blank=True, on_delete=models.PROTECT, related_name="dispatch_guards"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_dispatch_guard"
        unique_together = [("namespace", "student", "attendance_date", "disclosure_family", "destination_key")]

    def __str__(self):
        return f"Guard {self.student}/{self.attendance_date}/{self.destination_key}"


class OutboxEvent(models.Model):
    """
    Transactional outbox: written in the same transaction as the notification change.
    Relay reads this and publishes to Celery broker.
    Guarantees at-least-once delivery to workers; workers handle idempotency.
    """
    class EventTypeChoices(models.TextChoices):
        NOTIFICATION_QUEUED = "notification_queued", _("Notification queued")
        NOTIFICATION_CANCELLED = "notification_cancelled", _("Notification cancelled")
        SUMMARY_RECOMPUTE_NEEDED = "summary_recompute_needed", _("Summary recompute needed")
        RECONCILIATION_RUN = "reconciliation_run", _("Reconciliation run")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(
        _("event type"), max_length=64, choices=EventTypeChoices.choices
    )
    # Payload contains only stable IDs, never phone numbers or message text
    payload = models.JSONField(_("payload"), default=dict)
    due_at = models.DateTimeField(_("due at"), null=True, blank=True)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    is_published = models.BooleanField(_("published"), default=False)
    retry_count = models.PositiveSmallIntegerField(_("retry count"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_outbox_event"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["is_published", "due_at"]),
        ]


class DispatchControl(models.Model):
    """
    Global dispatch control singleton.
    Sender processes must match dispatcher_generation to send.
    Pausing is immediate; resuming requires explicit administrator action.
    After restore, live sending is disarmed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_globally_paused = models.BooleanField(_("globally paused"), default=False)
    pause_reason = models.CharField(_("pause reason"), max_length=512, blank=True)
    paused_at = models.DateTimeField(_("paused at"), null=True, blank=True)
    paused_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pause_actions",
    )
    # Only send on or after this date (prevents restore replay)
    approved_earliest_send_date = models.DateField(
        _("approved earliest send date"), null=True, blank=True,
        help_text="Set explicitly by administrator after restore to prevent replay.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_dispatch_control"

    def __str__(self):
        return f"DispatchControl (paused={self.is_globally_paused})"

