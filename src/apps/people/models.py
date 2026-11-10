"""
People models: Student, Guardian, contacts, enrollment.

Design:
- Students have stable UUIDs. Hall-ticket is a string (never the PK).
- Guardian is a person, not a phone number. Contact is separate.
- Contact authorization is per student/purpose, not inherited by siblings.
- Phone numbers are stored E.164; normalized via phonenumbers library.
- Missing/invalid numbers are quarantined, not silently guessed.
"""
import uuid
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField


class EnrollmentStatusChoices(models.TextChoices):
    ACTIVE = "active", _("Active")
    TRANSFERRED = "transferred", _("Transferred")
    READMITTED = "readmitted", _("Readmitted")
    WITHDRAWN = "withdrawn", _("Withdrawn")
    COMPLETED = "completed", _("Completed")
    ARCHIVED = "archived", _("Archived")


class Student(models.Model):
    """
    Institute student with a stable internal UUID.
    Hall-ticket/roll number is a string; treat as an opaque identifier.
    Never match students by name alone.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Hall-ticket is unique within the institute; treated as a string.
    hall_ticket_number = models.CharField(
        _("hall ticket number"), max_length=64, unique=True,
        help_text="String identifier. Format validated by configurable rules, not a hard-coded regex.",
    )
    full_name = models.CharField(_("full name"), max_length=255)
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True,
                                     help_text="Inactive students are excluded from future attendance/notifications.")
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    archived_reason = models.CharField(_("archived reason"), max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="students_created",
    )

    class Meta:
        db_table = "people_student"
        verbose_name = _("student")
        verbose_name_plural = _("students")
        ordering = ["hall_ticket_number"]

    def __str__(self):
        return f"{self.hall_ticket_number} — {self.full_name}"


class StudentIdentifierHistory(models.Model):
    """
    Tracks prior hall-ticket numbers/aliases for a student.
    Prevents reuse of an identifier across different students.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="identifier_history")
    prior_hall_ticket = models.CharField(_("prior hall ticket"), max_length=64)
    valid_from = models.DateField(_("valid from"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    correction_reason = models.CharField(_("correction reason"), max_length=512, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_student_identifier_history"
        ordering = ["-valid_from"]


class Enrollment(models.Model):
    """
    Places a student in a teaching term/section with a date range.
    One primary active placement at a time (enforced by service layer).
    Transfer/readmission creates a new interval.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    admission_batch = models.ForeignKey(
        "academics.AdmissionBatch", on_delete=models.PROTECT, related_name="enrollments"
    )
    regulation = models.ForeignKey(
        "academics.AcademicRegulation", null=True, blank=True,
        on_delete=models.PROTECT, related_name="enrollments",
    )
    term = models.ForeignKey(
        "academics.TeachingTerm", on_delete=models.PROTECT, related_name="enrollments"
    )
    section = models.ForeignKey(
        "academics.ClassSection", on_delete=models.PROTECT, related_name="enrollments"
    )
    status = models.CharField(
        _("status"), max_length=32, choices=EnrollmentStatusChoices.choices,
        default=EnrollmentStatusChoices.ACTIVE,
    )
    valid_from = models.DateField(_("valid from"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True,
                                   help_text="Null = still active.")
    entry_event = models.CharField(
        _("entry event"), max_length=64, blank=True,
        help_text="e.g., 'admission', 'lateral_entry', 'readmission', 'transfer'.",
    )
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_enrollment"
        ordering = ["-valid_from"]

    def __str__(self):
        return f"{self.student} in {self.term} Sec {self.section.section_code}"

    def is_active_on(self, target_date: date) -> bool:
        if not self.status == EnrollmentStatusChoices.ACTIVE:
            return False
        if self.valid_from > target_date:
            return False
        if self.valid_until and self.valid_until < target_date:
            return False
        return True


class SubjectEnrollment(models.Model):
    """Links a student to a specific subject offering (required for electives)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="subject_enrollments")
    offering = models.ForeignKey(
        "academics.SubjectOffering", on_delete=models.PROTECT, related_name="student_enrollments"
    )
    valid_from = models.DateField(_("valid from"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    is_exempted = models.BooleanField(_("exempted"), default=False)
    exemption_reason = models.CharField(_("exemption reason"), max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_subject_enrollment"
        ordering = ["-valid_from"]


class LabGroupMembership(models.Model):
    """Explicit lab group membership with date range."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="lab_memberships")
    lab_group = models.ForeignKey(
        "academics.LabGroup", on_delete=models.PROTECT, related_name="memberships"
    )
    valid_from = models.DateField(_("valid from"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_lab_group_membership"


class Guardian(models.Model):
    """
    A guardian person — name and relationship, NOT a phone number.
    A guardian may have multiple contacts and be linked to multiple students (siblings).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(_("full name"), max_length=255)
    relationship_default = models.CharField(
        _("default relationship"), max_length=64, blank=True,
        help_text="e.g., 'Father', 'Mother', 'Guardian'. May vary per student link.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_guardian"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class ContactStatusChoices(models.TextChoices):
    UNVERIFIED = "unverified", _("Unverified")
    ACTIVE = "active", _("Active")
    INVALID = "invalid", _("Invalid — quarantined")
    OPT_OUT = "opt_out", _("Opted out")


class GuardianContact(models.Model):
    """
    One phone number for a guardian.
    Stored E.164; normalization uses phonenumbers library with configured region.
    Invalid numbers are quarantined (status=INVALID), not silently dropped.
    A phone number may be shared across guardians (siblings); never globally unique.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="contacts")
    # Raw value as entered (preserved)
    raw_number = models.CharField(_("raw number"), max_length=32)
    # Normalized E.164 (blank if normalization failed)
    normalized_number = PhoneNumberField(
        _("normalized number (E.164)"), blank=True, null=True,
        help_text="Normalized via phonenumbers library. Empty if normalization failed.",
    )
    normalization_error = models.CharField(
        _("normalization error"), max_length=256, blank=True, default="",
        help_text="Populated if normalization failed.",
    )
    status = models.CharField(
        _("status"), max_length=32, choices=ContactStatusChoices.choices,
        default=ContactStatusChoices.UNVERIFIED,
    )
    is_primary = models.BooleanField(_("primary contact"), default=True)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_guardian_contact"

    def __str__(self):
        return f"{self.guardian} — {self.normalized_number or self.raw_number} ({self.status})"

    @property
    def is_eligible_for_sms(self) -> bool:
        """Phone is eligible to receive SMS notifications."""
        return (
            self.status == ContactStatusChoices.ACTIVE
            and self.normalized_number is not None
            and str(self.normalized_number).strip() != ""
        )


class NotificationPreferenceChoices(models.TextChoices):
    ENABLED = "enabled", _("Enabled")
    PAUSED = "paused", _("Paused — temporary")
    DISABLED = "disabled", _("Disabled")


class StudentGuardianLink(models.Model):
    """
    Links a student to a guardian with relationship and notification settings.
    Multiple links per student allowed; one is designated primary notification recipient.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="student_links")
    contact = models.ForeignKey(
        GuardianContact, on_delete=models.PROTECT, related_name="student_links",
        help_text="Which guardian contact to use for this student's notifications.",
    )
    relationship = models.CharField(_("relationship"), max_length=64, blank=True,
                                     help_text="e.g., 'Father', 'Mother'.")
    is_designated_recipient = models.BooleanField(
        _("designated notification recipient"), default=False,
        help_text="If True, this link receives absence notifications for this student.",
    )
    priority = models.PositiveSmallIntegerField(_("priority"), default=1,
                                                 help_text="Lower = higher priority.")
    notification_preference = models.CharField(
        _("notification preference"), max_length=32,
        choices=NotificationPreferenceChoices.choices,
        default=NotificationPreferenceChoices.ENABLED,
    )
    pause_until = models.DateField(_("paused until"), null=True, blank=True)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_student_guardian_link"
        ordering = ["priority"]

    def __str__(self):
        return f"{self.student} ← {self.guardian} ({self.relationship})"

    def is_eligible_for_notification(self, as_of: date | None = None) -> bool:
        today = as_of or date.today()
        if self.notification_preference == NotificationPreferenceChoices.DISABLED:
            return False
        if self.notification_preference == NotificationPreferenceChoices.PAUSED:
            if not self.pause_until or self.pause_until >= today:
                return False
        if self.valid_from and self.valid_from > today:
            return False
        if self.valid_until and self.valid_until < today:
            return False
        return self.is_designated_recipient and self.contact.is_eligible_for_sms


class ContactAuthorizationStatusChoices(models.TextChoices):
    PENDING = "pending", _("Pending review")
    AUTHORIZED = "authorized", _("Authorized")
    REVOKED = "revoked", _("Revoked")


class ContactAuthorization(models.Model):
    """
    Institute-approved authorization for disclosing a student's information
    to a guardian contact. Per student and disclosure purpose.
    Not legal compliance documentation — the institute must separately verify.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_guardian_link = models.ForeignKey(
        StudentGuardianLink, on_delete=models.CASCADE, related_name="authorizations"
    )
    disclosure_purpose = models.CharField(
        _("disclosure purpose"), max_length=64, default="absence_notification",
        help_text="e.g., 'absence_notification'. Separate purposes have separate authorizations.",
    )
    status = models.CharField(
        _("status"), max_length=32, choices=ContactAuthorizationStatusChoices.choices,
        default=ContactAuthorizationStatusChoices.PENDING,
    )
    authorized_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contact_authorizations",
    )
    effective_from = models.DateField(_("effective from"), null=True, blank=True)
    effective_until = models.DateField(_("effective until"), null=True, blank=True)
    evidence_reference = models.CharField(
        _("evidence reference"), max_length=512, blank=True,
        help_text="Reference to supporting document/process.",
    )
    opt_out_requested_at = models.DateTimeField(_("opt-out requested at"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_contact_authorization"

    def is_active_on(self, target_date: date) -> bool:
        if self.status != ContactAuthorizationStatusChoices.AUTHORIZED:
            return False
        if self.effective_from and self.effective_from > target_date:
            return False
        if self.effective_until and self.effective_until < target_date:
            return False
        return True

