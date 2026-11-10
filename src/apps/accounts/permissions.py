"""
Permission/authorization helpers for Avanthi Attendance.

Usage in views:
    from apps.accounts.permissions import require_role, get_user_scope

Design:
- Every backend operation checks permissions independently.
- Never trust URL parameters or client-supplied scope identifiers alone.
- Scoped role grants are evaluated per request with the current grant set.
- Mixins for class-based views; decorators for function-based views.
"""
import functools
from typing import Callable

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.accounts.models import RoleChoices, ScopedRoleGrant, User


def get_active_grants(user: User, role: str | None = None, as_of=None):
    """Return active grants for user, optionally filtered by role."""
    qs = user.active_grants(as_of=as_of)
    if role:
        qs = qs.filter(role=role)
    return qs


def has_role(user: User, role: str, as_of=None) -> bool:
    """Check if user has ANY active grant for the given role."""
    if not user.is_authenticated:
        return False
    return get_active_grants(user, role=role, as_of=as_of).exists()


def is_admin(user: User) -> bool:
    return user.is_authenticated and (
        user.is_superuser or has_role(user, RoleChoices.ADMIN)
    )


def can_access_department(user: User, department_id, as_of=None) -> bool:
    """
    Admin/principal can access all; HOD only their department; others: False.
    Faculty access is per-offering, not department-wide.
    """
    if not user.is_authenticated:
        return False
    if is_admin(user) or has_role(user, RoleChoices.PRINCIPAL):
        return True
    # HOD: must have an active HOD grant for this department
    return ScopedRoleGrant.objects.filter(
        user=user,
        role=RoleChoices.HOD,
        department_id_ref=department_id,
        is_active=True,
    ).filter(
        __import__("django.db.models", fromlist=["Q"]).Q(valid_until__isnull=True) |
        __import__("django.db.models", fromlist=["Q"]).Q(valid_until__gte=(as_of or __import__("datetime").date.today()))
    ).exists()


def can_access_offering(user: User, offering_id, as_of=None) -> bool:
    """
    Admin/principal: all; HOD: department-scoped check needed separately.
    Faculty: only their assigned offerings.
    """
    if not user.is_authenticated:
        return False
    if is_admin(user) or has_role(user, RoleChoices.PRINCIPAL):
        return True
    if has_role(user, RoleChoices.ATTENDANCE_OFFICER):
        return True
    return ScopedRoleGrant.objects.filter(
        user=user,
        role__in=[RoleChoices.FACULTY, RoleChoices.HOD, RoleChoices.MENTOR],
        offering_id_ref=offering_id,
        is_active=True,
    ).exists()


class RoleRequiredMixin(LoginRequiredMixin):
    """Mixin that requires one or more roles."""
    required_roles: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not any(has_role(request.user, r) for r in self.required_roles):
            if not is_admin(request.user):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin):
    """Only institute administrators."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not is_admin(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def require_admin(view_func: Callable) -> Callable:
    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_admin(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped

