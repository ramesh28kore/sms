"""Role-scoped operational dashboard."""

import csv
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.models import RoleChoices, ScopeTypeChoices, ScopedRoleGrant
from apps.audit.services import record_event
from apps.attendance.models import (
    AttendanceRecord,
    AttendanceStatusChoices,
    DailyAttendanceSummary,
    DailySummaryDecisionChoices,
)
from apps.institution.models import Department, InstituteSettings
from apps.notifications.models import (
    DailyNotificationIntent,
    Notification,
    NotificationStatusChoices,
)
from apps.people.models import Enrollment, EnrollmentStatusChoices
from apps.scheduling.models import (
    AttendanceRegisterStatusChoices,
    AttendanceSession,
    AttendanceSessionStatusChoices,
)


@dataclass(frozen=True)
class DashboardScope:
    institute_wide: bool
    department_ids: tuple
    section_ids: tuple
    offering_ids: tuple
    label: str


def _dashboard_scope(user, today, export_only=False):
    if user.is_superuser:
        return DashboardScope(True, (), (), (), "Institute-wide")

    grants = ScopedRoleGrant.objects.filter(
        user=user,
        is_active=True,
        valid_from__lte=today,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=today))
    if export_only:
        grants = grants.filter(can_export=True)

    global_roles = {
        RoleChoices.ADMIN,
        RoleChoices.PRINCIPAL,
        RoleChoices.ATTENDANCE_OFFICER,
    }
    if grants.filter(
        role__in=global_roles,
        scope_type=ScopeTypeChoices.INSTITUTE,
    ).exists():
        return DashboardScope(True, (), (), (), "Institute-wide")

    department_ids = tuple(
        grants.filter(
            role=RoleChoices.HOD,
        ).filter(
            Q(scope_type=ScopeTypeChoices.DEPARTMENT) | Q(department_id_ref__isnull=False)
        ).values_list("department_id_ref", flat=True)
    )
    section_ids = tuple(
        grants.filter(
            role=RoleChoices.MENTOR,
        ).filter(
            Q(scope_type=ScopeTypeChoices.SECTION) | Q(section_id_ref__isnull=False)
        ).values_list("section_id_ref", flat=True)
    )
    offering_ids = tuple(
        grants.filter(
            role=RoleChoices.FACULTY,
        ).filter(
            Q(scope_type=ScopeTypeChoices.OFFERING) | Q(offering_id_ref__isnull=False)
        ).values_list("offering_id_ref", flat=True)
    )

    if not (department_ids or section_ids or offering_ids):
        if grants.filter(role=RoleChoices.FACULTY).exists():
            return DashboardScope(False, (), (), (), "Faculty (No active offerings)")
        if grants.filter(role=RoleChoices.HOD).exists():
            return DashboardScope(False, (), (), (), "Department HOD")
        if grants.filter(role=RoleChoices.MENTOR).exists():
            return DashboardScope(False, (), (), (), "Class Mentor")
        raise PermissionDenied

    labels = []
    if department_ids:
        codes = Department.objects.filter(id__in=department_ids).values_list("code", flat=True)
        labels.extend(f"Department {code}" for code in codes)
    if section_ids:
        labels.append(f"{len(section_ids)} assigned section(s)")
    if offering_ids:
        labels.append(f"{len(offering_ids)} assigned subject offering(s)")
    return DashboardScope(
        False,
        department_ids,
        section_ids,
        offering_ids,
        ", ".join(labels),
    )


def _active_enrollments(today):
    return Enrollment.objects.filter(
        status=EnrollmentStatusChoices.ACTIVE,
        valid_from__lte=today,
        student__is_active=True,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=today))


def _scoped_student_ids(scope, today):
    enrollment_scope = Q()
    if scope.department_ids:
        enrollment_scope |= Q(section__term__branch__department_id__in=scope.department_ids)
    if scope.section_ids:
        enrollment_scope |= Q(section_id__in=scope.section_ids)
    return _active_enrollments(today).filter(enrollment_scope).values("student_id").distinct()


def _scoped_sessions(scope, today):
    sessions = AttendanceSession.objects.filter(session_date=today)
    if scope.institute_wide:
        return sessions

    session_scope = Q()
    if scope.department_ids:
        session_scope |= Q(offering__term__branch__department_id__in=scope.department_ids)
    if scope.section_ids:
        session_scope |= Q(section_id__in=scope.section_ids) | Q(
            offering__sections__id__in=scope.section_ids
        )
    if scope.offering_ids:
        session_scope |= Q(offering_id__in=scope.offering_ids)
    return sessions.filter(session_scope).distinct()


@login_required
@never_cache
def dashboard(request):
    institute = InstituteSettings.objects.order_by("created_at").first()
    institute_timezone = institute.timezone if institute else settings.INSTITUTE_TIMEZONE
    zone = ZoneInfo(institute_timezone)
    now_local = timezone.localtime(timezone.now(), zone)
    today = now_local.date()
    scope = _dashboard_scope(request.user, today)

    incomplete_registers = _scoped_sessions(scope, today).filter(
        Q(session_status=AttendanceSessionStatusChoices.UNRESOLVED)
        | Q(
            session_status=AttendanceSessionStatusChoices.HELD,
            register_status=AttendanceRegisterStatusChoices.DRAFT,
        )
    ).count()

    context = {
        "institute_name": (
            institute.institute_name
            if institute
            else "Avanthi Institute of Engineering and Technology"
        ),
        "institute_timezone": institute_timezone,
        "sms_mode": institute.sms_mode if institute else "simulator",
        "today": today,
        "now_local": now_local,
        "scope_label": scope.label,
        "incomplete_registers": incomplete_registers,
        "summary_visible": bool(
            scope.institute_wide or scope.department_ids or scope.section_ids
        ),
        "absent_students": None,
        "queued_notices": None,
        "accepted_notices": None,
        "blocked_notices": None,
        "blocked_intents": None,
        "failed_notices": None,
        "unknown_notices": None,
    }

    if context["summary_visible"]:
        student_ids = _scoped_student_ids(scope, today)
        summaries = DailyAttendanceSummary.objects.filter(
            summary_date=today,
            is_dirty=False,
            student__is_active=True,
            student_id__in=student_ids,
        )
        context["absent_students"] = summaries.filter(
            decision=DailySummaryDecisionChoices.ELIGIBLE_ABSENT
        ).values("student_id").distinct().count()

        notices = Notification.objects.filter(
            intent__attendance_date=today,
            intent__student_id__in=student_ids,
            is_simulation=(context["sms_mode"] != "live"),
        )
        status_counts = notices.aggregate(
            queued=Count("id", filter=Q(status=NotificationStatusChoices.QUEUED)),
            accepted=Count(
                "id", filter=Q(status=NotificationStatusChoices.DISPATCH_ACCEPTED)
            ),
            blocked=Count("id", filter=Q(status=NotificationStatusChoices.BLOCKED)),
            failed=Count("id", filter=Q(status=NotificationStatusChoices.FAILED)),
            unknown=Count(
                "id", filter=Q(status=NotificationStatusChoices.UNKNOWN_OUTCOME)
            ),
        )
        context["blocked_intents"] = DailyNotificationIntent.objects.filter(
            attendance_date=today,
            student_id__in=student_ids,
            intent_status=NotificationStatusChoices.BLOCKED,
        ).count()
        context.update(
            queued_notices=status_counts["queued"],
            accepted_notices=status_counts["accepted"],
            blocked_notices=status_counts["blocked"],
            failed_notices=status_counts["failed"],
            unknown_notices=status_counts["unknown"],
        )

    from apps.accounts.permissions import is_admin
    context["is_admin"] = is_admin(request.user)

    return render(request, "dashboard/index.html", context)


def _report_date(value, default):
    if not value:
        return default, None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return default, "Enter a valid date."
    return parsed, None


def _attendance_report_rows(scope, start_date, end_date):
    sessions = _scoped_session_queryset(scope, start_date, end_date)
    record_scope = _record_scope(scope)

    return list(
        sessions.order_by()
        .values(
            "offering__subject__code",
            "offering__subject__title",
            "offering__term__branch__code",
            "offering__term__study_year",
            "offering__term__semester",
            "register_status",
        )
        .annotate(
            held_sessions=Count("id", distinct=True),
            present_or_late=Count(
                "attendance_records__id",
                filter=record_scope
                & Q(
                    attendance_records__status__in=[
                        AttendanceStatusChoices.PRESENT,
                        AttendanceStatusChoices.LATE,
                    ]
                ),
                distinct=True,
            ),
            absent=Count(
                "attendance_records__id",
                filter=record_scope
                & Q(attendance_records__status=AttendanceStatusChoices.ABSENT),
                distinct=True,
            ),
            excused=Count(
                "attendance_records__id",
                filter=record_scope
                & Q(attendance_records__status=AttendanceStatusChoices.EXCUSED),
                distinct=True,
            ),
            unmarked=Count(
                "attendance_records__id",
                filter=record_scope
                & Q(attendance_records__status=AttendanceStatusChoices.UNMARKED),
                distinct=True,
            ),
        )
        .order_by(
            "offering__term__branch__code",
            "offering__term__study_year",
            "offering__term__semester",
            "register_status",
            "offering__subject__code",
        )
    )


def _scoped_session_queryset(scope, start_date, end_date):
    sessions = AttendanceSession.objects.filter(
        session_date__range=(start_date, end_date),
        session_status=AttendanceSessionStatusChoices.HELD,
    )
    if scope.institute_wide:
        return sessions

    session_scope = Q()
    if scope.department_ids:
        session_scope |= Q(
            offering__term__branch__department_id__in=scope.department_ids
        )
    if scope.section_ids:
        session_scope |= Q(section_id__in=scope.section_ids) | Q(
            offering__sections__id__in=scope.section_ids
        )
    if scope.offering_ids:
        session_scope |= Q(offering_id__in=scope.offering_ids)
    return sessions.filter(session_scope).distinct()


def _record_scope(scope):
    record_scope = Q()
    if not scope.institute_wide:
        if scope.department_ids:
            record_scope |= Q(
                roster_members__enrollment__section__term__branch__department_id__in=scope.department_ids
            )
        if scope.section_ids:
            record_scope |= Q(
                roster_members__enrollment__section_id__in=scope.section_ids
            )
    return record_scope & Q(
        roster_members__student_id=F("attendance_records__student_id"),
        roster_members__is_expected=True,
    )


def _date_range_errors(start_date, end_date, today, start_error, end_error):
    errors = [error for error in (start_error, end_error) if error]
    if start_date > end_date:
        errors.append("The start date must be on or before the end date.")
    if end_date > today:
        errors.append("Future dates are not available in attendance reports.")
    return errors


@login_required
@never_cache
def attendance_report(request):
    institute = InstituteSettings.objects.order_by("created_at").first()
    institute_timezone = institute.timezone if institute else settings.INSTITUTE_TIMEZONE
    today = timezone.localtime(
        timezone.now(), ZoneInfo(institute_timezone)
    ).date()
    scope = _dashboard_scope(request.user, today)
    start_date, start_error = _report_date(
        request.GET.get("start"), today.replace(day=1)
    )
    end_date, end_error = _report_date(request.GET.get("end"), today)
    errors = _date_range_errors(
        start_date, end_date, today, start_error, end_error
    )
    try:
        _dashboard_scope(request.user, today, export_only=True)
        can_export = True
    except PermissionDenied:
        can_export = False

    return render(
        request,
        "reports/attendance.html",
        {
            "institute_name": (
                institute.institute_name
                if institute
                else "Avanthi Institute of Engineering and Technology"
            ),
            "today": today,
            "start_date": start_date,
            "end_date": end_date,
            "scope_label": scope.label,
            "errors": errors,
            "rows": [] if errors else _attendance_report_rows(
                scope, start_date, end_date
            ),
            "can_export": can_export,
            "policy_notice": (
                "Counts only. No academic percentage or eligibility decision is "
                "calculated here. Configure an institute-approved policy for the "
                "applicable admission batch and regulation before reporting percentages."
            ),
        },
    )


@login_required
@never_cache
def attendance_report_sessions(request):
    institute = InstituteSettings.objects.order_by("created_at").first()
    institute_timezone = institute.timezone if institute else settings.INSTITUTE_TIMEZONE
    today = timezone.localtime(
        timezone.now(), ZoneInfo(institute_timezone)
    ).date()
    scope = _dashboard_scope(request.user, today)
    start_date, start_error = _report_date(
        request.GET.get("start"), today.replace(day=1)
    )
    end_date, end_error = _report_date(request.GET.get("end"), today)
    errors = _date_range_errors(
        start_date, end_date, today, start_error, end_error
    )

    page_obj = None
    if not errors:
        session_scope = _record_scope(scope)
        sessions = (
            _scoped_session_queryset(scope, start_date, end_date)
            .select_related("offering__subject", "offering__term__branch", "section")
            .annotate(
                expected_records=Count(
                    "attendance_records__id",
                    filter=session_scope
                    & Q(
                        attendance_records__status__in=[
                            AttendanceStatusChoices.PRESENT,
                            AttendanceStatusChoices.ABSENT,
                            AttendanceStatusChoices.LATE,
                            AttendanceStatusChoices.EXCUSED,
                            AttendanceStatusChoices.UNMARKED,
                        ]
                    ),
                    distinct=True,
                )
            )
            .order_by("-session_date", "scheduled_start_utc", "id")
        )
        page_obj = Paginator(sessions, 50).get_page(request.GET.get("page"))

    return render(
        request,
        "reports/sessions.html",
        {
            "start_date": start_date,
            "end_date": end_date,
            "scope_label": scope.label,
            "errors": errors,
            "page_obj": page_obj,
        },
    )


@login_required
@never_cache
def attendance_report_session_detail(request, session_id):
    institute = InstituteSettings.objects.order_by("created_at").first()
    institute_timezone = institute.timezone if institute else settings.INSTITUTE_TIMEZONE
    today = timezone.localtime(
        timezone.now(), ZoneInfo(institute_timezone)
    ).date()
    scope = _dashboard_scope(request.user, today)
    session = get_object_or_404(
        _scoped_session_queryset(
            scope,
            date.min,
            today,
        ).select_related(
            "offering__subject",
            "offering__term__branch",
            "section",
            "lab_group",
        ),
        pk=session_id,
    )
    records = (
        AttendanceRecord.objects.filter(
            session=session,
            session__roster_members__student_id=F("student_id"),
            session__roster_members__is_expected=True,
        )
        .select_related("student")
        .order_by("student__hall_ticket_number")
    )
    return render(
        request,
        "reports/session_detail.html",
        {
            "session": session,
            "records": records,
            "scope_label": scope.label,
        },
    )


def _csv_cell(value):
    text = str(value if value is not None else "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


@login_required
@never_cache
@require_POST
def attendance_report_export(request):
    institute = InstituteSettings.objects.order_by("created_at").first()
    institute_timezone = institute.timezone if institute else settings.INSTITUTE_TIMEZONE
    today = timezone.localtime(
        timezone.now(), ZoneInfo(institute_timezone)
    ).date()
    scope = _dashboard_scope(request.user, today, export_only=True)
    start_date, start_error = _report_date(
        request.POST.get("start"), today.replace(day=1)
    )
    end_date, end_error = _report_date(request.POST.get("end"), today)
    errors = _date_range_errors(
        start_date, end_date, today, start_error, end_error
    )
    if errors:
        return HttpResponse("; ".join(errors), status=400, content_type="text/plain")

    rows = _attendance_report_rows(scope, start_date, end_date)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="attendance-counts-{start_date:%Y%m%d}-{end_date:%Y%m%d}.csv"'
    )
    response["Cache-Control"] = "private, no-store"
    writer = csv.writer(response)
    writer.writerow(
        [
            "branch",
            "study_year",
            "semester",
            "subject_code",
            "subject_title",
            "register_state",
            "held_sessions",
            "present_or_late_records",
            "absent_records",
            "excused_records",
            "unmarked_records",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                _csv_cell(row["offering__term__branch__code"]),
                row["offering__term__study_year"],
                row["offering__term__semester"],
                _csv_cell(row["offering__subject__code"]),
                _csv_cell(row["offering__subject__title"]),
                _csv_cell(row["register_status"]),
                row["held_sessions"],
                row["present_or_late"],
                row["absent"],
                row["excused"],
                row["unmarked"],
            ]
        )

    record_event(
        action="report.attendance.csv_export",
        actor=request.user,
        metadata={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "row_count": len(rows),
        },
        request=request,
    )
    return response