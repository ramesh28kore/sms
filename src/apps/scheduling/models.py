"""
Scheduling models:
AcademicCalendarDay, TimetableVersion, TimetableSlot,
ScheduleException, DailySchedulePlan, StudentDayExpectation, AttendanceSession.

Design:
- Published timetable versions are immutable; changes create new versions.
- DailySchedulePlan must be sealed before absence decisions are made.
- StudentDayExpectation is per-student, so one missing session doesn't block others.
- AttendanceSession is the logical occurrence (one per timetable slot per date).
  Multi-period labs = one AttendanceSession covering multiple period spans.
"""
import uuid
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _


class AcademicCalendarDay(models.Model):
    """
    Institute academic calendar. One row per date per scope.
    Institute-wide default; branch/section overrides allowed.
    """
    class DayTypeChoices(models.TextChoices):
        INSTRUCTIONAL = "instructional", _("Instructional Day")
        HOLIDAY = "holiday", _("Holiday")
        EXAM = "exam", _("Examination Day")
        COMPENSATORY = "compensatory", _("Compensatory Class")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar_date = models.DateField(_("date"))
    day_type = models.CharField(
        _("day type"), max_length=32, choices=DayTypeChoices.choices,
        default=DayTypeChoices.INSTRUCTIONAL,
    )
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    # Scope (null = institute-wide)
    branch = models.ForeignKey(
        "academics.Branch", null=True, blank=True, on_delete=models.CASCADE,
        related_name="calendar_days",
    )
    section = models.ForeignKey(
        "academics.ClassSection", null=True, blank=True, on_delete=models.CASCADE,
        related_name="calendar_days",
    )
    # Priority: section > branch > institute-wide
    override_priority = models.PositiveSmallIntegerField(_("override priority"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduling_calendar_day"
        ordering = ["calendar_date"]
        # Note: uniqueness per scope enforced at service layer (complex multi-null FK)

    def __str__(self):
        scope = f" [{self.section or self.branch or 'institute'}]"
        return f"{self.calendar_date} {self.get_day_type_display()}{scope}"

    @property
    def is_instructional(self) -> bool:
        return self.day_type in (
            self.DayTypeChoices.INSTRUCTIONAL,
            self.DayTypeChoices.COMPENSATORY,
        )


class TimetableVersionStatusChoices(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    SUPERSEDED = "superseded", _("Superseded")


class TimetableVersion(models.Model):
    """
    Versioned timetable. Published versions are immutable.
    Changes create a new version; prior version becomes SUPERSEDED.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    term = models.ForeignKey(
        "academics.TeachingTerm", on_delete=models.PROTECT, related_name="timetable_versions"
    )
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    effective_from = models.DateField(_("effective from"))
    effective_until = models.DateField(_("effective until"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=TimetableVersionStatusChoices.choices,
        default=TimetableVersionStatusChoices.DRAFT,
    )
    description = models.CharField(_("description"), max_length=512, blank=True)
    published_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="timetables_published",
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scheduling_timetable_version"
        ordering = ["-effective_from", "-version_number"]

    def __str__(self):
        return f"v{self.version_number} ({self.term}) from {self.effective_from} [{self.status}]"


class WeekdayChoices(models.IntegerChoices):
    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class TimetableSlot(models.Model):
    """
    One recurring slot in a timetable version.
    Multi-period labs have one logical slot but multiple period_spans entries.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(
        TimetableVersion, on_delete=models.CASCADE, related_name="slots"
    )
    weekday = models.IntegerField(_("weekday"), choices=WeekdayChoices.choices)
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    offering = models.ForeignKey(
        "academics.SubjectOffering", on_delete=models.PROTECT, related_name="timetable_slots"
    )
    section = models.ForeignKey(
        "academics.ClassSection", null=True, blank=True, on_delete=models.PROTECT,
        related_name="timetable_slots",
    )
    lab_group = models.ForeignKey(
        "academics.LabGroup", null=True, blank=True, on_delete=models.PROTECT,
        related_name="timetable_slots",
    )
    # Logical occurrence key: stable across version copies
    logical_occurrence_key = models.CharField(
        _("logical occurrence key"), max_length=64, blank=True,
        help_text="Stable key linking equivalent slots across timetable versions.",
    )
    # For multi-period labs: list of period numbers covered
    period_spans = models.JSONField(
        _("period spans"), default=list, blank=True,
        help_text="List of period numbers (e.g., [3,4]) covered by this slot. Single period: [1].",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scheduling_timetable_slot"
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time}–{self.end_time} {self.offering}"


class ScheduleException(models.Model):
    """
    Per-date override: extra class, replacement, cancellation.
    Explicit replacement link prevents double-counting original + replacement.
    """
    class ExceptionTypeChoices(models.TextChoices):
        CANCELLED = "cancelled", _("Cancelled")
        EXTRA = "extra", _("Extra Class")
        REPLACEMENT = "replacement", _("Replacement")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exception_date = models.DateField(_("date"))
    exception_type = models.CharField(
        _("type"), max_length=32, choices=ExceptionTypeChoices.choices
    )
    # Original slot being affected (may be null for pure extra classes)
    original_slot = models.ForeignKey(
        TimetableSlot, null=True, blank=True, on_delete=models.PROTECT,
        related_name="exceptions",
    )
    # For replacements: the new slot that replaces the original
    replacement_slot = models.ForeignKey(
        TimetableSlot, null=True, blank=True, on_delete=models.PROTECT,
        related_name="replacement_for",
    )
    # For extra classes: direct specification
    offering = models.ForeignKey(
        "academics.SubjectOffering", null=True, blank=True,
        on_delete=models.PROTECT, related_name="schedule_exceptions",
    )
    section = models.ForeignKey(
        "academics.ClassSection", null=True, blank=True, on_delete=models.PROTECT,
        related_name="schedule_exceptions",
    )
    reason = models.CharField(_("reason"), max_length=512, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scheduling_schedule_exception"
        ordering = ["exception_date"]


class DailySchedulePlan(models.Model):
    """
    Generated and sealed plan for one local date.
    Must be sealed before absence classification can proceed.
    Missing plan = gap, not evidence that no class was expected.
    """
    class SealStatusChoices(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SEALED = "sealed", _("Sealed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_date = models.DateField(_("date"), unique=True)
    seal_status = models.CharField(
        _("seal status"), max_length=16, choices=SealStatusChoices.choices,
        default=SealStatusChoices.DRAFT,
    )
    sealed_at = models.DateTimeField(_("sealed at"), null=True, blank=True)
    sealed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="plans_sealed",
    )
    source_timetable_versions = models.ManyToManyField(
        TimetableVersion, related_name="daily_plans", blank=True
    )
    # Revision for optimistic concurrency
    revision = models.PositiveIntegerField(_("revision"), default=1)
    coverage_notes = models.TextField(_("coverage notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduling_daily_plan"
        ordering = ["-plan_date"]

    def __str__(self):
        return f"Plan {self.plan_date} [{self.seal_status}]"


class StudentDayExpectation(models.Model):
    """
    Per-student expectation set for a day: which sessions they're expected in.
    One student's missing expectation does not block classification of others.
    """
    class SealStatusChoices(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SEALED = "sealed", _("Sealed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="day_expectations")
    expectation_date = models.DateField(_("date"))
    daily_plan = models.ForeignKey(DailySchedulePlan, on_delete=models.PROTECT, related_name="student_expectations")
    # Snapshot of which sessions this student is expected in
    expected_session_ids = models.JSONField(
        _("expected session IDs"), default=list,
        help_text="List of AttendanceSession UUIDs this student is expected to attend.",
    )
    seal_status = models.CharField(
        _("seal status"), max_length=16, choices=SealStatusChoices.choices,
        default=SealStatusChoices.DRAFT,
    )
    sealed_at = models.DateTimeField(_("sealed at"), null=True, blank=True)
    source_plan_revision = models.PositiveIntegerField(_("plan revision"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduling_student_day_expectation"
        unique_together = [("student", "expectation_date")]
        ordering = ["-expectation_date"]


class AttendanceSessionStatusChoices(models.TextChoices):
    UNRESOLVED = "unresolved", _("Unresolved (pending attendance)")
    HELD = "held", _("Held")
    CANCELLED = "cancelled", _("Cancelled / Not Conducted")


class AttendanceRegisterStatusChoices(models.TextChoices):
    DRAFT = "draft", _("Draft")
    FINALIZED = "finalized", _("Finalized")


class AttendanceSession(models.Model):
    """
    One logical attendance session (may span multiple periods for labs).
    Unique per plan lineage. Superseded sessions are not counted.
    Multi-period labs are ONE session.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daily_plan = models.ForeignKey(
        DailySchedulePlan, on_delete=models.PROTECT, related_name="sessions"
    )
    offering = models.ForeignKey(
        "academics.SubjectOffering", on_delete=models.PROTECT, related_name="sessions"
    )
    section = models.ForeignKey(
        "academics.ClassSection", null=True, blank=True,
        on_delete=models.PROTECT, related_name="sessions",
    )
    lab_group = models.ForeignKey(
        "academics.LabGroup", null=True, blank=True,
        on_delete=models.PROTECT, related_name="sessions",
    )
    timetable_slot = models.ForeignKey(
        TimetableSlot, null=True, blank=True, on_delete=models.PROTECT,
        related_name="sessions",
        help_text="Source timetable slot. Null for extra/exception sessions.",
    )
    schedule_exception = models.ForeignKey(
        ScheduleException, null=True, blank=True, on_delete=models.PROTECT,
        related_name="sessions",
    )
    session_date = models.DateField(_("session date"))
    # UTC timestamps for the session window
    scheduled_start_utc = models.DateTimeField(_("scheduled start (UTC)"), null=True, blank=True)
    scheduled_end_utc = models.DateTimeField(_("scheduled end (UTC)"), null=True, blank=True)
    # Period spans (for labs)
    period_spans = models.JSONField(_("period spans"), default=list)
    session_status = models.CharField(
        _("session status"), max_length=16, choices=AttendanceSessionStatusChoices.choices,
        default=AttendanceSessionStatusChoices.UNRESOLVED,
    )
    register_status = models.CharField(
        _("register status"), max_length=16, choices=AttendanceRegisterStatusChoices.choices,
        default=AttendanceRegisterStatusChoices.DRAFT,
    )
    # Optimistic concurrency
    revision = models.PositiveIntegerField(_("revision"), default=1)
    plan_revision_at_creation = models.PositiveIntegerField(_("plan revision"), default=1)
    # Cancellation
    cancelled_reason = models.CharField(_("cancelled reason"), max_length=512, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sessions_cancelled",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduling_attendance_session"
        ordering = ["session_date", "scheduled_start_utc"]

    def __str__(self):
        return f"{self.offering} on {self.session_date} [{self.session_status}/{self.register_status}]"

