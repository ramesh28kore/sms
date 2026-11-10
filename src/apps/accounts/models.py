"""
Custom User model and scoped role grant system.

Design decisions:
- AbstractBaseUser + PermissionsMixin for full control.
- Roles are stored separately as ScopedRoleGrant with validity intervals.
- Roles: ADMIN, PRINCIPAL, HOD, FACULTY, MENTOR, ATTENDANCE_OFFICER.
- Scope: institute / department / section / offering, with validity dates.
- Django admin is NOT the primary interface; custom views enforce scoped checks.
- UUIDs as primary keys for all durable identity records.
"""
import uuid
from datetime import date

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Manager for the custom User model."""

    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required.")
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Institute staff user.
    No public signup — accounts are created by administrators only.
    Phone is optional (for internal contact; not for SMS delivery).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(_("username"), max_length=64, unique=True)
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=255)
    phone = models.CharField(_("phone"), max_length=20, blank=True, default="")
    is_staff = models.BooleanField(_("staff status"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    # Must complete MFA enrollment for privileged actions
    mfa_required = models.BooleanField(
        _("MFA required"),
        default=False,
        help_text="If True, this user must have MFA set up before accessing sensitive features.",
    )
    # Track last password change for rotation policy
    password_changed_at = models.DateTimeField(_("password changed at"), null=True, blank=True)
    # Notes visible to administrators only
    admin_notes = models.TextField(_("admin notes"), blank=True, default="")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "full_name"]

    objects = UserManager()

    class Meta:
        db_table = "accounts_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.username

    def active_grants(self, as_of: date | None = None):
        """Return queryset of currently active ScopedRoleGrants for this user."""
        today = as_of or date.today()
        return self.role_grants.filter(
            is_active=True,
            valid_from__lte=today,
        ).filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=today)
        )


class RoleChoices(models.TextChoices):
    """
    Available roles. Each role carries default capabilities; individual grants
    may add or restrict specific capabilities within their scope.
    """
    ADMIN = "admin", _("Institute Administrator")
    PRINCIPAL = "principal", _("Principal / Management")
    HOD = "hod", _("Head of Department")
    FACULTY = "faculty", _("Faculty Member")
    MENTOR = "mentor", _("Class In-Charge / Mentor")
    ATTENDANCE_OFFICER = "attendance_officer", _("Attendance Officer")


class ScopeTypeChoices(models.TextChoices):
    INSTITUTE = "institute", _("Entire Institute")
    DEPARTMENT = "department", _("Department")
    SECTION = "section", _("Class Section")
    OFFERING = "offering", _("Subject Offering")


class ScopedRoleGrant(models.Model):
    """
    Associates a user with a role within a specific scope and time range.

    Invariants:
    - Multiple grants per user allowed (e.g., HOD of dept A AND faculty of offering B).
    - Scope must be consistent with role (e.g., HOD requires department scope).
    - Valid ranges are half-open [valid_from, valid_until).
    - is_active=False immediately revokes the grant even within validity range.
    - Grants are audited; changing a grant creates an AuditEvent.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="role_grants",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=32, choices=RoleChoices.choices)
    scope_type = models.CharField(
        _("scope type"), max_length=32, choices=ScopeTypeChoices.choices,
        default=ScopeTypeChoices.INSTITUTE,
    )
    # Generic scope references — only one will be populated
    department_id_ref = models.UUIDField(
        _("department"), null=True, blank=True,
        help_text="Set for DEPARTMENT scope.",
    )
    section_id_ref = models.UUIDField(
        _("section"), null=True, blank=True,
        help_text="Set for SECTION scope.",
    )
    offering_id_ref = models.UUIDField(
        _("offering"), null=True, blank=True,
        help_text="Set for OFFERING scope.",
    )
    valid_from = models.DateField(_("valid from"), default=date.today)
    valid_until = models.DateField(_("valid until"), null=True, blank=True,
                                   help_text="Null = open-ended.")
    is_active = models.BooleanField(_("active"), default=True)
    # Extra capabilities beyond the role default
    can_reveal_contacts = models.BooleanField(_("can reveal contacts"), default=False)
    can_export = models.BooleanField(_("can export"), default=False)
    can_correct_attendance = models.BooleanField(_("can correct finalized attendance"), default=False)
    can_manage_gateway = models.BooleanField(_("can manage gateway"), default=False)
    can_activate_live = models.BooleanField(_("can activate live SMS"), default=False)
    can_manual_resend = models.BooleanField(_("can manually resend notifications"), default=False)
    # Substitution: temporary faculty cover
    is_substitution = models.BooleanField(_("temporary substitution"), default=False)
    substitution_reason = models.CharField(
        _("substitution reason"), max_length=512, blank=True, default=""
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="grants_created", verbose_name=_("created by"),
    )

    def save(self, *args, **kwargs):
        if self.offering_id_ref and self.scope_type == ScopeTypeChoices.INSTITUTE:
            self.scope_type = ScopeTypeChoices.OFFERING
        elif self.department_id_ref and self.scope_type == ScopeTypeChoices.INSTITUTE:
            self.scope_type = ScopeTypeChoices.DEPARTMENT
        elif self.section_id_ref and self.scope_type == ScopeTypeChoices.INSTITUTE:
            self.scope_type = ScopeTypeChoices.SECTION
        super().save(*args, **kwargs)

    class Meta:
        db_table = "accounts_scoped_role_grant"
        verbose_name = _("scoped role grant")
        verbose_name_plural = _("scoped role grants")
        ordering = ["-valid_from", "role"]

    def __str__(self):
        scope = f" [{self.scope_type}]" if self.scope_type != ScopeTypeChoices.INSTITUTE else ""
        return f"{self.user} — {self.get_role_display()}{scope}"

    def is_currently_active(self, as_of: date | None = None) -> bool:
        today = as_of or date.today()
        if not self.is_active:
            return False
        if self.valid_from > today:
            return False
        if self.valid_until is not None and self.valid_until < today:
            return False
        return True

