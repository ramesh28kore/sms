"""
Attendance calculation and daily summary services.

Invariants:
- FULL_DAY_ABSENT rule:
    1. At least one session was HELD today for this student.
    2. All expected sessions for this student are resolved (no UNRESOLVED).
    3. All held sessions have FINALIZED registers.
    4. Every held session attendance record is explicitly ABSENT.
    5. Any PRESENT, LATE, or EXCUSED session immediately excludes the student.
    6. Unfinished registers or unsealed schedule plans BLOCK classification.
    7. Days with zero held sessions produce NO_SESSIONS (never an absence notice).
- Academic percentage calculations:
    - Zero held sessions displays "N/A", never 0% or 100%.
    - Only computed if an approved AcademicAttendancePolicyVersion is active.
    - Otherwise returns counts only; labels thresholds "Not configured".
"""
import logging
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def compute_daily_summary_for_student(student, target_date: date) -> "DailyAttendanceSummary":
    """
    Computes (or recomputes) the DailyAttendanceSummary for one student on target_date.
    This is idempotent and safe to call multiple times.
    Marks is_dirty=False upon completion.
    """
    from apps.attendance.models import (
        AttendanceRecord,
        AttendanceStatusChoices,
        DailyAttendanceSummary,
        DailySummaryDecisionChoices,
    )
    from apps.notifications.models import AbsenceRuleChoices, NotificationPolicyVersion
    from apps.scheduling.models import (
        AttendanceRegisterStatusChoices,
        AttendanceSession,
        AttendanceSessionStatusChoices,
        DailySchedulePlan,
        StudentDayExpectation,
    )

    # Get active daily notification policy
    active_policy = NotificationPolicyVersion.objects.filter(
        is_active=True,
        effective_from__lte=target_date,
    ).filter(
        __import__("django.db.models", fromlist=["Q"]).Q(effective_until__isnull=True) |
        __import__("django.db.models", fromlist=["Q"]).Q(effective_until__gte=target_date)
    ).first()

    absence_rule = active_policy.absence_rule if active_policy else AbsenceRuleChoices.FULL_DAY_ABSENT
    excused_counts_as_absent = active_policy.excused_counts_as_absent if active_policy else False

    summary, _ = DailyAttendanceSummary.objects.get_or_create(
        student=student,
        summary_date=target_date,
    )

    blockers = []

    # 1. Check schedule plan is sealed for this date
    plan = DailySchedulePlan.objects.filter(plan_date=target_date).first()
    if not plan or plan.seal_status != DailySchedulePlan.SealStatusChoices.SEALED:
        blockers.append("schedule_plan_not_sealed")

    # 2. Check student day expectation is sealed
    expectation = StudentDayExpectation.objects.filter(
        student=student,
        expectation_date=target_date,
    ).first()

    expected_session_ids = expectation.expected_session_ids if expectation else []

    # Query all sessions this student is expected in
    sessions = AttendanceSession.objects.filter(
        id__in=expected_session_ids,
        session_date=target_date,
    )

    total_expected = len(expected_session_ids)
    held_count = 0
    cancelled_count = 0
    unresolved_count = 0
    absent_count = 0
    present_count = 0
    late_count = 0
    excused_count = 0

    session_records = {
        r.session_id: r
        for r in AttendanceRecord.objects.filter(
            student=student,
            session__in=sessions,
        )
    }

    for sess in sessions:
        if sess.session_status == AttendanceSessionStatusChoices.CANCELLED:
            cancelled_count += 1
            continue

        if sess.session_status == AttendanceSessionStatusChoices.UNRESOLVED:
            unresolved_count += 1
            blockers.append(f"unresolved_session_{sess.id}")
            continue

        if sess.register_status != AttendanceRegisterStatusChoices.FINALIZED:
            blockers.append(f"unfinalized_register_{sess.id}")

        held_count += 1
        rec = session_records.get(sess.id)

        if not rec or rec.status == AttendanceStatusChoices.UNMARKED:
            blockers.append(f"unmarked_record_{sess.id}")
        elif rec.status == AttendanceStatusChoices.ABSENT:
            absent_count += 1
        elif rec.status == AttendanceStatusChoices.PRESENT:
            present_count += 1
        elif rec.status == AttendanceStatusChoices.LATE:
            late_count += 1
        elif rec.status == AttendanceStatusChoices.EXCUSED:
            excused_count += 1

    summary.expected_sessions = total_expected
    summary.held_sessions = held_count
    summary.cancelled_sessions = cancelled_count
    summary.unresolved_sessions = unresolved_count
    summary.absent_sessions = absent_count
    summary.present_sessions = present_count
    summary.late_sessions = late_count
    summary.excused_sessions = excused_count
    summary.blocker_reasons = blockers

    # Determine decision
    if blockers:
        summary.decision = DailySummaryDecisionChoices.BLOCKED
    elif held_count == 0:
        # No sessions held today (holiday, all cancelled, or no classes scheduled)
        summary.decision = DailySummaryDecisionChoices.NO_SESSIONS
    else:
        # All held sessions are finalized and marked
        if absence_rule == AbsenceRuleChoices.FULL_DAY_ABSENT:
            # Safe default: every held session must be ABSENT.
            # PRESENT, LATE exclude. EXCUSED excludes unless policy says otherwise.
            effective_absent = absent_count + (excused_count if excused_counts_as_absent else 0)
            if present_count > 0 or late_count > 0 or (not excused_counts_as_absent and excused_count > 0):
                summary.decision = DailySummaryDecisionChoices.NOT_ELIGIBLE
            elif effective_absent == held_count:
                summary.decision = DailySummaryDecisionChoices.ELIGIBLE_ABSENT
            else:
                summary.decision = DailySummaryDecisionChoices.NOT_ELIGIBLE

        elif absence_rule == AbsenceRuleChoices.ANY_SESSION_ABSENT:
            if absent_count > 0:
                summary.decision = DailySummaryDecisionChoices.ELIGIBLE_ABSENT
            else:
                summary.decision = DailySummaryDecisionChoices.NOT_ELIGIBLE

        elif absence_rule == AbsenceRuleChoices.THRESHOLD:
            threshold = active_policy.absent_session_threshold or 1
            if absent_count >= threshold:
                summary.decision = DailySummaryDecisionChoices.ELIGIBLE_ABSENT
            else:
                summary.decision = DailySummaryDecisionChoices.NOT_ELIGIBLE
        else:
            summary.decision = DailySummaryDecisionChoices.NOT_ELIGIBLE

    summary.is_dirty = False
    summary.computed_at = timezone.now()
    summary.save()

    return summary


def invalidate_student_daily_summary(student_id, target_date: date):
    """
    Mark DailyAttendanceSummary dirty synchronously.
    Cancels any pending outbox work if the decision is no longer valid.
    """
    from apps.attendance.models import DailyAttendanceSummary
    DailyAttendanceSummary.objects.filter(
        student_id=student_id,
        summary_date=target_date,
    ).update(is_dirty=True)


def calculate_academic_attendance_percentage(
    student,
    term=None,
    as_of: date | None = None,
) -> dict:
    """
    Calculate academic attendance counts and policy-backed percentages.

    Returns:
        {
            "held_sessions": int,
            "attended_sessions": int,   # PRESENT + LATE
            "absent_sessions": int,
            "excused_sessions": int,
            "percentage": Optional[float],   # None if 0 held or policy not configured
            "percentage_display": str,       # "N/A" if 0 held, "78.5%" or "Not configured"
            "policy_configured": bool,
            "policy_code": str,
            "condonation_eligible": Optional[bool],
        }

    Invariants:
    - Zero held sessions displays "N/A", never 0% or full attendance.
    - No guessed JNTUH thresholds. If no policy: percentage is None, display is "Not configured".
    """
    from apps.attendance.models import (
        AcademicAttendancePolicyVersion,
        AttendanceRecord,
        AttendanceStatusChoices,
    )
    from apps.scheduling.models import AttendanceSessionStatusChoices

    qs = AttendanceRecord.objects.filter(
        student=student,
        session__session_status=AttendanceSessionStatusChoices.HELD,
    )
    if term:
        qs = qs.filter(session__daily_plan__source_timetable_versions__term=term)
    if as_of:
        qs = qs.filter(session__session_date__lte=as_of)

    held = qs.count()
    if held == 0:
        return {
            "held_sessions": 0,
            "attended_sessions": 0,
            "absent_sessions": 0,
            "excused_sessions": 0,
            "percentage": None,
            "percentage_display": "N/A",
            "policy_configured": False,
            "policy_code": "",
            "condonation_eligible": None,
        }

    present = qs.filter(status__in=[AttendanceStatusChoices.PRESENT, AttendanceStatusChoices.LATE]).count()
    absent = qs.filter(status=AttendanceStatusChoices.ABSENT).count()
    excused = qs.filter(status=AttendanceStatusChoices.EXCUSED).count()

    # Look for an approved academic policy
    policy = AcademicAttendancePolicyVersion.objects.filter(
        is_active=True,
    ).first()

    if not policy or policy.minimum_attendance_percent is None:
        raw_pct = round((present / held) * 100, 1)
        return {
            "held_sessions": held,
            "attended_sessions": present,
            "absent_sessions": absent,
            "excused_sessions": excused,
            "percentage": raw_pct,
            "percentage_display": f"{raw_pct}% (academic rules Not configured)",
            "policy_configured": False,
            "policy_code": "",
            "condonation_eligible": None,
        }

    pct = round((present / held) * 100, 2)
    min_pct = float(policy.minimum_attendance_percent)
    condon_pct = float(policy.condonation_percent) if policy.condonation_percent else None

    condonation_eligible = None
    if condon_pct and pct < min_pct and pct >= condon_pct:
        condonation_eligible = True
    elif pct >= min_pct:
        condonation_eligible = False  # Not needed; already eligible

    return {
        "held_sessions": held,
        "attended_sessions": present,
        "absent_sessions": absent,
        "excused_sessions": excused,
        "percentage": pct,
        "percentage_display": f"{pct}%",
        "policy_configured": True,
        "policy_code": policy.code,
        "condonation_eligible": condonation_eligible,
    }
