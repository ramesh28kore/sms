"""
Institution settings model.
Singleton per installation. Changes are versioned and audited.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class InstituteSettings(models.Model):
    """
    Singleton row representing the institute's configurable identity.
    Example data must be replaced by an administrator before live use.
    No campus address, college code, or official affiliation is hard-coded.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # --- Identity ---
    institute_name = models.CharField(
        _("institute name"), max_length=255,
        default="Avanthi Institute of Engineering and Technology",
        help_text="Official institute name as approved by the administrator.",
    )
    approved_short_name = models.CharField(
        _("approved short name"), max_length=64, default="Avanthi Institute",
        help_text="Short name used in SMS messages. Preview and confirm before live use.",
    )
    campus_identifier = models.CharField(
        _("campus identifier"), max_length=128, blank=True, default="",
        help_text="Optional campus code/identifier. Leave blank if not applicable.",
    )
    academic_context_label = models.CharField(
        _("academic context label"), max_length=64, default="B.Tech | JNTUH",
        help_text="Label displayed in the UI (e.g., 'B.Tech | JNTUH'). Configurable.",
    )
    official_contact = models.CharField(
        _("official contact"), max_length=255, blank=True, default="",
        help_text="Contact used in SMS messages (e.g., phone/email). Set before live use.",
    )
    # --- Locale ---
    timezone = models.CharField(
        _("institute timezone"), max_length=64, default="Asia/Kolkata",
        help_text="IANA timezone name. Default: Asia/Kolkata. Confirm before live use.",
    )
    phone_region = models.CharField(
        _("phone region"), max_length=4, default="IN",
        help_text="ISO 3166-1 alpha-2 country code for phone parsing. Default: IN.",
    )
    # --- Academic year ---
    current_academic_year_label = models.CharField(
        _("current academic year label"), max_length=32, blank=True, default="",
        help_text="e.g. '2026-27'. Set by administrator.",
    )
    # --- Mode ---
    class ModeChoices(models.TextChoices):
        SIMULATOR = "simulator", _("Simulator (no real SMS)")
        LIVE = "live", _("Live (real SMS)")

    sms_mode = models.CharField(
        _("SMS mode"), max_length=16, choices=ModeChoices.choices,
        default=ModeChoices.SIMULATOR,
        help_text="SIMULATOR mode is the safe default. Live requires explicit administrator activation.",
    )
    live_activated_at = models.DateTimeField(
        _("live activated at"), null=True, blank=True,
        help_text="Set when an administrator explicitly activates live mode.",
    )
    live_activated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="live_activations",
        verbose_name=_("live activated by"),
    )
    # Dispatcher generation: increments on every live activation / restart-disarm
    dispatcher_generation = models.PositiveIntegerField(
        _("dispatcher generation"), default=0,
        help_text="Incremented on each live activation. Workers must match this to send.",
    )
    # --- Wizard state ---
    setup_wizard_completed = models.BooleanField(
        _("setup wizard completed"), default=False,
    )
    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_settings"
        verbose_name = _("institute settings")
        verbose_name_plural = _("institute settings")

    def __str__(self):
        return self.institute_name

    @classmethod
    def get(cls) -> "InstituteSettings":
        """Get (or create with defaults) the singleton settings record."""
        obj, _ = cls.objects.get_or_create(pk=list(cls.objects.values_list("id", flat=True)[:1])[0]
                                            if cls.objects.exists()
                                            else uuid.uuid4())
        return obj

    @classmethod
    def get_or_create_singleton(cls) -> "InstituteSettings":
        qs = cls.objects.all()
        if qs.exists():
            return qs.first()
        return cls.objects.create()


class Department(models.Model):
    """
    Academic department. Stable code; display name may change.
    Historical labels are preserved via audit.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        _("department code"), max_length=32, unique=True,
        help_text="Stable short code (e.g., 'CSE', 'ECE'). Do not change after use.",
    )
    display_name = models.CharField(_("display name"), max_length=255)
    is_active = models.BooleanField(_("active"), default=True)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_department"
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.display_name}"

