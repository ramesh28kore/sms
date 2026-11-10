"""
Attendance models:
SessionRosterMember, AttendanceRecord, AttendanceChange,
AttendanceFinalization, DailyAttendanceSummary, AcademicAttendancePolicyVersion.

Design:
- AttendanceRecord is per student per session (unique).
- UNMARKED ≠ ABSENT. Finalization rejects unresolved UNMARKED entries.
- DailyAttendanceSummary is a derived projection (unique per student/date).
- Corrections require reason + audited role; never silent reopen.
- Academic policy is separate from daily notification policy.
  Zero held sessions → N/A, never 0% or full attendance.
"""
import uuid
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _


class AttendanceStatusChoices(models.TextChoices):
    UNMARKED = "unmarked", _("Unmarked")
    PRESENT = "present", _("Present")
    ABSENT = "absent", _("Absent")
    LATE = "late", _("Late")
    EXCUSED = "excused", _("Excused")


class SessionRosterMember(models.Model):
    """
    Frozen roster snapshot: which students are expected in a session.
    Immutable after session finalization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "scheduling.AttendanceSession", on_delete=models.PROTECT, related_name="roster_members"
    )
    student = models.ForeignKey(
        "people.Student", on_delete=models.PROTECT, related_name="roster_memberships"
    )
    enrollment = models.ForeignKey(
        "people.Enrollment", on_delete=models.PROTECT, related_name="roster_memberships"
    )
    # Snapshot of department/section at roster creation time
    section_snapshot = models.CharField(_("section snapshot"), max_length=64, blank=True)
    department_snapshot = models.CharField(_("department snapshot"), max_length=64, blank=True)
    is_expected = models.BooleanField(
        _("expected"), default=True,
        help_text="False if student joined late/transferred but is included for reference.",
    )
    roster_revision = models.PositiveIntegerField(_("roster revision"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_session_roster_member"
        unique_together = [("session", "student")]
        ordering = ["student__hall_ticket_number"]

    def __str__(self):
        return f"{self.student} in {self.session}"


class AttendanceRecord(models.Model):
    """
    One attendance record per student per session.
    UNMARKED is a valid, distinct status (not equal to ABSENT).
    Status must be explicitly set to ABSENT; never inferred.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "scheduling.AttendanceSession", on_delete=models.PROTECT, related_name="attendance_records"
    )
    student = models.ForeignKey(
        "people.Student", on_delete=models.PROTECT, related_name="attendance_records"
    )
    status = models.CharField(
        _("status"), max_length=16, choices=AttendanceStatusChoices.choices,
        default=AttendanceStatusChoices.UNMARKED,
    )
    # Leave/on-duty reason stored separately; not included in SMS
    leave_reason = models.CharField(
        _("leave/on-duty reason"), max_length=512, blank=True, default="",
        help_text="Stored securely; not included in SMS text.",
    )
    # Optimistic concurrency version
    version = models.PositiveIntegerField(_("version"), default=1)
    last_updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="attendance_records_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_record"
        unique_together = [("session", "student")]
        ordering = ["student__hall_ticket_number"]

    def __str__(self):
        return f"{self.student} — {self.session} → {self.status}"


class AttendanceChangeReasonChoices(models.TextChoices):
    INITIAL_MARK = "initial_mark", _("Initial mark")
    DRAFT_UPDATE = "draft_update", _("Draft update")
    CORRECTION = "correction", _("Authorized correction")
    IMPORT = "import", _("Imported")
    FINALIZATION = "finalization", _("Finalized")


class AttendanceChange(models.Model):
    """
    Append-only history of attendance record changes.
    Required for corrections to finalized registers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.CASCADE, related_name="changes"
    )
    session_revision_at_change = models.PositiveIntegerField()
    old_status = models.CharField(max_length=16, choices=AttendanceStatusChoices.choices)
    new_status = models.CharField(max_length=16, choices=AttendanceStatusChoices.choices)
    change_reason = models.CharField(
        _("change reason"), max_length=32, choices=AttendanceChangeReasonChoices.choices
    )
    reason_description = models.TextField(_("reason description"), blank=True)
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="attendance_changes",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    # Correction authorization reference (for finalized corrections)
    correction_authorized_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="correction_authorizations",
    )

    class Meta:
        db_table = "attendance_change"
        ordering = ["recorded_at"]


class AttendanceFinalization(models.Model):
    """
    Immutable record of session finalization.
    Captures roster revision, record versions, and totals at the moment of finalization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        "scheduling.AttendanceSession", on_delete=models.PROTECT, related_name="finalization"
    )
    finalized_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="finalizations"
    )
    finalized_at = models.DateTimeField(auto_now_add=True)
    roster_revision = models.PositiveIntegerField()
    session_revision = models.PositiveIntegerField()
    total_expected = models.PositiveIntegerField()
    total_present = models.PositiveIntegerField()
    total_absent = models.PositiveIntegerField()
    total_late = models.PositiveIntegerField()
    total_excused = models.PositiveIntegerField()
    # Snapshot of all statuses at finalization time
    record_snapshot = models.JSONField(
        _("record snapshot"), default=dict,
        help_text="Snapshot of {student_id: status} at finalization. Immutable evidence.",
    )

    class Meta:
        db_table = "attendance_finalization"

    def __str__(self):
        return f"Finalization of {self.session} at {self.finalized_at}"


class DailySummaryDecisionChoices(models.TextChoices):
    NOT_COMPUTED = "not_computed", _("Not yet computed")
    BLOCKED = "blocked", _("Blocked — incomplete data")
    ELIGIBLE_ABSENT = "eligible_absent", _("Eligible — absent (notification triggered)")
    NOT_ELIGIBLE = "not_eligible", _("Not eligible — present/late/excused/no sessions")
    NO_SESSIONS = "no_sessions", _("No instructional sessions today")


class DailyAttendanceSummary(models.Model):
    """
    One derived daily attendance summary per student per date.
    This is a projection; it must be recomputed after any relevant change.
    is_dirty=True means recomputation is pending; stale data never authorizes dispatch.

    Decision codes:
    - ELIGIBLE_ABSENT: triggers notification pipeline
    - BLOCKED: unfinished/unresolved sessions; cannot classify
    - NOT_ELIGIBLE: student had a present/late/excused session
    - NO_SESSIONS: no instructional sessions held (no notification)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="daily_summaries")
    summary_date = models.DateField(_("date"))
    decision = models.CharField(
        _("decision"), max_length=32, choices=DailySummaryDecisionChoices.choices,
        default=DailySummaryDecisionChoices.NOT_COMPUTED,
    )
    # Detailed counts
    expected_sessions = models.PositiveIntegerField(default=0)
    held_sessions = models.PositiveIntegerField(default=0)
    cancelled_sessions = models.PositiveIntegerField(default=0)
    unresolved_sessions = models.PositiveIntegerField(default=0)
    absent_sessions = models.PositiveIntegerField(default=0)
    present_sessions = models.PositiveIntegerField(default=0)
    late_sessions = models.PositiveIntegerField(default=0)
    excused_sessions = models.PositiveIntegerField(default=0)
    # Blocking reasons (populated when decision=BLOCKED)
    blocker_reasons = models.JSONField(_("blocker reasons"), default=list,
                                       help_text="List of reason codes explaining why classification is blocked.")
    # Source fingerprint for cache invalidation
    source_fingerprint = models.CharField(_("source fingerprint"), max_length=128, blank=True)
    is_dirty = models.BooleanField(
        _("dirty"), default=False,
        help_text="True if recomputation is pending. Stale summary never authorizes dispatch.",
    )
    computed_at = models.DateTimeField(_("computed at"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_daily_summary"
        unique_together = [("student", "summary_date")]
        ordering = ["-summary_date"]

    def __str__(self):
        return f"{self.student} on {self.summary_date}: {self.decision}"

    @property
    def is_absent_all_day(self) -> bool:
        """True only when decision is ELIGIBLE_ABSENT and summary is not dirty."""
        return (
            not self.is_dirty
            and self.decision == DailySummaryDecisionChoices.ELIGIBLE_ABSENT
        )


class AcademicAttendancePolicyVersion(models.Model):
    """
    Institute-approved academic attendance policy (for percentage reports only).
    NOT the daily notification policy.
    Thresholds remain 'Not configured' until an approved source is provided.
    Never auto-label students detained or exam-ineligible.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("policy code"), max_length=64, unique=True)
    description = models.TextField(_("description"), blank=True)
    source_reference = models.CharField(
        _("source reference"), max_length=512,
        help_text="URL or document reference for the approved policy source.",
    )
    # Applicability
    regulation = models.ForeignKey(
        "academics.AcademicRegulation", null=True, blank=True,
        on_delete=models.PROTECT, related_name="attendance_policies",
    )
    admission_batch = models.ForeignKey(
        "academics.AdmissionBatch", null=True, blank=True,
        on_delete=models.PROTECT, related_name="attendance_policies",
    )
    effective_from = models.DateField(_("effective from"))
    effective_until = models.DateField(_("effective until"), null=True, blank=True)
    # Policy details (all configurable; none hard-coded)
    minimum_attendance_percent = models.DecimalField(
        _("minimum attendance %"), max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Set only from an approved source. Null = Not configured.",
    )
    counting_basis = models.CharField(
        _("counting basis"), max_length=64, blank=True,
        help_text="e.g., 'held_sessions', 'scheduled_sessions'. From approved source.",
    )
    lab_session_weight = models.PositiveSmallIntegerField(
        _("lab session weight"), default=1,
        help_text="How many sessions a lab occurrence counts as. 1 = same as lecture.",
    )
    condonation_percent = models.DecimalField(
        _("condonation %"), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    is_active = models.BooleanField(_("active"), default=True)
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_academic_policy"
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.code} (from {self.effective_from})"

