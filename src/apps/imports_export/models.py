"""
Imports/export models: ImportJob, ImportRow.
Staged CSV preview: no mutations during preview.
Atomic, idempotent commit.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class ImportJobTypeChoices(models.TextChoices):
    STUDENTS = "students", _("Students & Guardians")
    ATTENDANCE = "attendance", _("Attendance Records")


class ImportJobStatusChoices(models.TextChoices):
    PENDING_PREVIEW = "pending_preview", _("Pending Preview")
    PREVIEW_READY = "preview_ready", _("Preview Ready (validated)")
    COMMITTING = "committing", _("Committing")
    COMMITTED = "committed", _("Committed")
    FAILED = "failed", _("Failed")


class ImportJob(models.Model):
    """
    One staged CSV import job.
    Upload metadata + row validation happens in PREVIEW stage.
    No live DB mutations occur during preview.
    Commit is atomic and idempotent (checked by file_hash).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_type = models.CharField(
        _("import type"), max_length=32, choices=ImportJobTypeChoices.choices
    )
    status = models.CharField(
        _("status"), max_length=32, choices=ImportJobStatusChoices.choices,
        default=ImportJobStatusChoices.PENDING_PREVIEW,
    )
    original_filename = models.CharField(_("original filename"), max_length=255)
    file_hash = models.CharField(
        _("SHA-256 file hash"), max_length=64,
        help_text="Prevents duplicate submission of the same file.",
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="import_jobs"
    )
    # Column mapping configured by user
    column_mapping = models.JSONField(_("column mapping"), default=dict, blank=True)
    # Row counts
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    # Target scope
    teaching_term = models.ForeignKey(
        "academics.TeachingTerm", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="import_jobs",
    )
    committed_at = models.DateTimeField(_("committed at"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "imports_import_job"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.import_type} [{self.status}] by {self.uploaded_by}"


class ImportRow(models.Model):
    """
    One row within a staged import job.
    Stores raw values, validation errors, and resolved entities.
    """
    class RowStatusChoices(models.TextChoices):
        VALID = "valid", _("Valid")
        ERROR = "error", _("Error")
        WARNING = "warning", _("Warning")
        COMMITTED = "committed", _("Committed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField(_("row number"))
    raw_data = models.JSONField(_("raw data"), default=dict)
    errors = models.JSONField(_("errors"), default=list)
    warnings = models.JSONField(_("warnings"), default=list)
    status = models.CharField(
        _("status"), max_length=16, choices=RowStatusChoices.choices,
        default=RowStatusChoices.VALID,
    )
    # Action that will be taken on commit: 'create', 'update', 'skip'
    action_type = models.CharField(_("action type"), max_length=16, default="create")
    resolved_entity_id = models.CharField(_("resolved entity ID"), max_length=64, blank=True)

    class Meta:
        db_table = "imports_import_row"
        ordering = ["row_number"]

