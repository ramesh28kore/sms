"""
Academics models:
Programme, Branch, AdmissionBatch, AcademicRegulation,
AcademicYear, Semester/TeachingTerm, ClassSection, LabGroup,
Subject, SubjectOffering, FacultyAssignment.

Design:
- B.Tech Years I–IV with Semesters I/II are defaults, not code constants.
- All structural elements are configurable by administrators.
- Effective dates on most entities to support transfers, lateral entry, etc.
- No hard-coded JNTUH regulation codes or attendance thresholds.
"""
import uuid
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _


class Programme(models.Model):
    """
    Academic programme (e.g., B.Tech, M.Tech).
    Year/semester structure is configurable; B.Tech 4-year 2-sem is default.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("code"), max_length=32, unique=True)
    title = models.CharField(_("title"), max_length=255)
    duration_years = models.PositiveSmallIntegerField(_("duration (years)"), default=4)
    semesters_per_year = models.PositiveSmallIntegerField(_("semesters per year"), default=2)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_programme"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.title}"


class Branch(models.Model):
    """
    Branch/specialization within a programme and department.
    Example: CSE under B.Tech in Computer Science Department.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="branches")
    department = models.ForeignKey(
        "institution.Department", on_delete=models.PROTECT, related_name="branches"
    )
    code = models.CharField(_("branch code"), max_length=32)
    title = models.CharField(_("branch title"), max_length=255)
    is_active = models.BooleanField(_("active"), default=True)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_branch"
        unique_together = [("programme", "code")]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} ({self.programme.code})"


class AdmissionBatch(models.Model):
    """
    Admission cohort — the year students joined.
    Separate from current academic year/term.
    Required for lateral-entry and readmission history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("batch code"), max_length=32, unique=True,
                             help_text="e.g., '2023' or '2023-LE' for lateral entry.")
    label = models.CharField(_("label"), max_length=128)
    entry_year = models.PositiveSmallIntegerField(_("entry year"))
    is_lateral_entry = models.BooleanField(_("lateral entry"), default=False)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="admission_batches")
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_admission_batch"
        ordering = ["-entry_year", "code"]

    def __str__(self):
        return self.label


class AcademicRegulation(models.Model):
    """
    Academic regulation/syllabus code.
    No JNTUH-specific defaults. Source and applicability must be explicitly configured.
    Academic thresholds remain 'Not configured' until an approved source is provided.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("regulation code"), max_length=64, unique=True,
                             help_text="e.g., 'R22'. Set by administrator from approved source.")
    description = models.TextField(_("description"), blank=True)
    source_reference = models.CharField(
        _("source reference"), max_length=512, blank=True,
        help_text="URL or document reference for this regulation.",
    )
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="regulations")
    effective_from_batch = models.ForeignKey(
        AdmissionBatch, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="regulations",
        help_text="First admission batch this regulation applies to.",
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_regulation"
        ordering = ["code"]

    def __str__(self):
        return self.code


class AcademicYear(models.Model):
    """
    Calendar academic year (e.g., 2026-27).
    Separate from admission batch.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(_("label"), max_length=32, unique=True,
                              help_text="e.g., '2026-27'.")
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    is_current = models.BooleanField(_("current"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_academic_year"
        ordering = ["-start_date"]

    def __str__(self):
        return self.label


class TeachingTerm(models.Model):
    """
    One teaching semester in a specific academic year (e.g., AY2026-27, Sem I, Year III).
    Ties academic year + study year + semester ordinal + branch + date range.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="terms")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="terms")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="terms")
    study_year = models.PositiveSmallIntegerField(
        _("study year"), help_text="Year of study: 1, 2, 3, or 4 for B.Tech."
    )
    semester = models.PositiveSmallIntegerField(
        _("semester"), help_text="Semester ordinal within the study year (1 or 2)."
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    is_active = models.BooleanField(_("active"), default=True)
    label = models.CharField(
        _("label"), max_length=128, blank=True,
        help_text="Human-readable label (auto-generated if blank).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_teaching_term"
        unique_together = [("academic_year", "branch", "study_year", "semester")]
        ordering = ["academic_year", "study_year", "semester"]

    def __str__(self):
        return self.label or f"{self.branch} Y{self.study_year}S{self.semester} ({self.academic_year})"

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = f"{self.branch.code} Year {self.study_year} Sem {self.semester} ({self.academic_year.label})"
        super().save(*args, **kwargs)


class ClassSection(models.Model):
    """
    One class section within a teaching term (e.g., CSE Y2 S1 Section A).
    Unique within its term; never globally identified by name alone.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    term = models.ForeignKey(TeachingTerm, on_delete=models.PROTECT, related_name="sections")
    section_code = models.CharField(_("section code"), max_length=16,
                                     help_text="e.g., 'A', 'B', '1'.")
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_class_section"
        unique_together = [("term", "section_code")]
        ordering = ["term", "section_code"]

    def __str__(self):
        return f"{self.term} — Sec {self.section_code}"


class LabGroup(models.Model):
    """
    Lab group within a section/offering. Membership is explicit and dated.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(ClassSection, on_delete=models.PROTECT, related_name="lab_groups")
    group_code = models.CharField(_("group code"), max_length=16, help_text="e.g., 'L1', 'L2'.")
    description = models.CharField(_("description"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_lab_group"
        unique_together = [("section", "group_code")]
        ordering = ["section", "group_code"]

    def __str__(self):
        return f"{self.section} — {self.group_code}"


class Subject(models.Model):
    """Reusable subject catalogue entry."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("subject code"), max_length=64, unique=True)
    title = models.CharField(_("title"), max_length=255)
    is_lab = models.BooleanField(_("is lab"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_subject"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.title}"


class SubjectOfferingTypeChoices(models.TextChoices):
    LECTURE = "lecture", _("Lecture")
    LAB = "lab", _("Laboratory")
    TUTORIAL = "tutorial", _("Tutorial")
    ELECTIVE = "elective", _("Elective")


class SubjectOffering(models.Model):
    """
    One teaching instance of a subject in a term for specific sections.
    Can span multiple sections (electives).
    Labs use their own period-counting rules (one logical session per lab period).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="offerings")
    term = models.ForeignKey(TeachingTerm, on_delete=models.PROTECT, related_name="offerings")
    sections = models.ManyToManyField(ClassSection, related_name="offerings", blank=True)
    delivery_type = models.CharField(
        _("delivery type"), max_length=16, choices=SubjectOfferingTypeChoices.choices,
        default=SubjectOfferingTypeChoices.LECTURE,
    )
    # Lab group that this offering serves (null = all students in the section)
    lab_group = models.ForeignKey(
        LabGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="offerings",
        help_text="Set for lab offerings with specific lab group roster.",
    )
    # Attendance counting: how many 'sessions' one lab run counts as
    # Defaults to 1 (one logical session per scheduled occurrence regardless of periods)
    session_count_per_occurrence = models.PositiveSmallIntegerField(
        _("session count per occurrence"), default=1,
        help_text="For academic percentage reporting only. 1 = one session per scheduled run.",
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "academics_subject_offering"
        ordering = ["term", "subject"]

    def __str__(self):
        return f"{self.subject.code} ({self.term})"


class FacultyAssignment(models.Model):
    """
    Authorizes a user (faculty) to teach a specific offering/section scope.
    Covers substitutions with validity dates.
    Expiry of a substitution removes the future ability to access sessions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="faculty_assignments"
    )
    offering = models.ForeignKey(SubjectOffering, on_delete=models.PROTECT, related_name="assignments")
    # Restricts to specific section or lab group if set; null means all sections in offering
    section = models.ForeignKey(
        ClassSection, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="faculty_assignments",
    )
    lab_group = models.ForeignKey(
        LabGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="faculty_assignments",
    )
    valid_from = models.DateField(_("valid from"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    is_substitution = models.BooleanField(_("substitution"), default=False)
    substitution_reason = models.CharField(_("substitution reason"), max_length=512, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="assignments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "academics_faculty_assignment"
        ordering = ["-valid_from"]

    def __str__(self):
        return f"{self.user} → {self.offering} (from {self.valid_from})"

    def is_currently_active(self, as_of: date | None = None) -> bool:
        today = as_of or date.today()
        if not self.is_active:
            return False
        if self.valid_from > today:
            return False
        if self.valid_until is not None and self.valid_until < today:
            return False
        return True

