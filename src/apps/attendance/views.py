from datetime import date
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.scheduling.models import AttendanceSession, AttendanceSessionStatusChoices, AttendanceRegisterStatusChoices
from apps.attendance.models import AttendanceRecord, AttendanceStatusChoices, AttendanceFinalization
from apps.attendance.services import compute_daily_summary_for_student
from apps.accounts.permissions import is_admin, can_access_offering


@login_required
def session_list_view(request):
    today = timezone.localdate()
    sessions = AttendanceSession.objects.filter(session_date=today).select_related("offering", "offering__subject", "section")

    # Faculty filtering
    if not is_admin(request.user):
        assigned_offerings = request.user.role_grants.filter(offering_id_ref__isnull=False, is_active=True).values_list("offering_id_ref", flat=True)
        sessions = sessions.filter(offering_id__in=assigned_offerings)

    return render(request, "attendance/session_list.html", {
        "sessions": sessions,
        "selected_date": today,
    })


@login_required
def session_register_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    records = session.attendance_records.all().select_related("student")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_draft":
            for r in records:
                val = request.POST.get(f"status_{r.student.id}")
                if val:
                    r.status = val
                    r.last_updated_by = request.user
                    r.save()
            from django.contrib import messages
            messages.success(request, "Draft attendance saved successfully.")
            return redirect("attendance:register", session_id=session.id)

        elif action == "finalize":
            # First apply submitted radio statuses
            for r in records:
                val = request.POST.get(f"status_{r.student.id}")
                if val:
                    r.status = val
                    r.last_updated_by = request.user
                    r.save()

            # Refresh to inspect updated statuses
            records = session.attendance_records.all().select_related("student")

            # Check for unresolved unmarked records
            unmarked = [r for r in records if r.status == AttendanceStatusChoices.UNMARKED]
            if unmarked:
                return render(request, "attendance/register.html", {
                    "session": session,
                    "records": records,
                    "error": f"Cannot finalize session: {len(unmarked)} students remain UNMARKED. UNMARKED must never mean ABSENT.",
                })

            session.session_status = AttendanceSessionStatusChoices.HELD
            session.register_status = AttendanceRegisterStatusChoices.FINALIZED
            session.revision += 1
            session.save()

            # Create or update AttendanceFinalization evidence
            snapshot = {str(r.student.id): r.status for r in records}
            AttendanceFinalization.objects.update_or_create(
                session=session,
                defaults={
                    "finalized_by": request.user,
                    "roster_revision": 1,
                    "session_revision": session.revision,
                    "total_expected": records.count(),
                    "total_present": sum(1 for r in records if r.status == AttendanceStatusChoices.PRESENT),
                    "total_absent": sum(1 for r in records if r.status == AttendanceStatusChoices.ABSENT),
                    "total_late": sum(1 for r in records if r.status == AttendanceStatusChoices.LATE),
                    "total_excused": sum(1 for r in records if r.status == AttendanceStatusChoices.EXCUSED),
                    "record_snapshot": snapshot,
                }
            )

            # Recompute daily summaries for affected students
            for r in records:
                compute_daily_summary_for_student(r.student, session.session_date)

            from django.contrib import messages
            messages.success(request, f"Attendance register for {session.offering} finalized successfully.")
            return redirect("attendance:register", session_id=session.id)

    return render(request, "attendance/register.html", {
        "session": session,
        "records": records,
    })

