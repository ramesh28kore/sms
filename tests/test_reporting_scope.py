"""Database-backed reporting access regression tests."""

from datetime import date

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory

from apps.accounts.models import RoleChoices, ScopedRoleGrant, ScopeTypeChoices, User
from apps.audit.models import AuditEvent
from apps.academics.models import (
    AcademicYear,
    AdmissionBatch,
    Branch,
    ClassSection,
    Programme,
    Subject,
    SubjectOffering,
    TeachingTerm,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatusChoices, SessionRosterMember
from apps.institution.models import Department
from apps.people.models import Enrollment, Student
from apps.reporting.views import (
    attendance_report,
    attendance_report_export,
    attendance_report_session_detail,
    attendance_report_sessions,
)
from apps.scheduling.models import (
    AttendanceRegisterStatusChoices,
    AttendanceSession,
    AttendanceSessionStatusChoices,
    DailySchedulePlan,
)


@pytest.mark.django_db
def test_hod_report_excludes_other_department_sessions():
    today = date.today()
    year_start = today.replace(month=1, day=1)
    year_end = today.replace(month=12, day=31)
    user = User.objects.create_user(
        username="scope-test-hod",
        email="scope-test-hod@example.test",
        password="test-only-password",
        full_name="Synthetic HOD",
    )
    allowed_department = Department.objects.create(
        code="SCOPE-A",
        display_name="Synthetic Department A",
    )
    hidden_department = Department.objects.create(
        code="SCOPE-B",
        display_name="Synthetic Department B",
    )
    programme = Programme.objects.create(code="SCOPE-BTECH", title="Synthetic B.Tech")
    academic_year = AcademicYear.objects.create(
        label=f"Scope test {today.year}",
        start_date=year_start,
        end_date=year_end,
    )
    batch = AdmissionBatch.objects.create(
        code=f"SCOPE-{today.year}",
        label="Synthetic scope test batch",
        entry_year=today.year,
        programme=programme,
    )
    plan = DailySchedulePlan.objects.create(
        plan_date=today,
        seal_status=DailySchedulePlan.SealStatusChoices.SEALED,
    )
    sessions = {}

    for suffix, department, subject_code in (
        ("A", allowed_department, "VISIBLE101"),
        ("B", hidden_department, "HIDDEN101"),
    ):
        branch = Branch.objects.create(
            programme=programme,
            department=department,
            code=f"SCOPE-{suffix}",
            title=f"Synthetic Branch {suffix}",
        )
        term = TeachingTerm.objects.create(
            academic_year=academic_year,
            programme=programme,
            branch=branch,
            study_year=1,
            semester=1,
            start_date=year_start,
            end_date=year_end,
        )
        section = ClassSection.objects.create(term=term, section_code="A")
        student = Student.objects.create(
            hall_ticket_number=f"SCOPE-{suffix}-{today.year}",
            full_name=f"Synthetic Student {suffix}",
        )
        enrollment = Enrollment.objects.create(
            student=student,
            admission_batch=batch,
            term=term,
            section=section,
            valid_from=year_start,
        )
        subject = Subject.objects.create(
            code=subject_code,
            title=(
                " =HYPERLINK(\"https://example.invalid\")"
                if suffix == "A"
                else "Synthetic subject"
            ),
        )
        offering = SubjectOffering.objects.create(subject=subject, term=term)
        offering.sections.add(section)
        session = AttendanceSession.objects.create(
            daily_plan=plan,
            offering=offering,
            section=section,
            session_date=today,
            session_status=AttendanceSessionStatusChoices.HELD,
            register_status=AttendanceRegisterStatusChoices.FINALIZED,
        )
        sessions[suffix] = session
        SessionRosterMember.objects.create(
            session=session,
            student=student,
            enrollment=enrollment,
        )
        AttendanceRecord.objects.create(
            session=session,
            student=student,
            status=AttendanceStatusChoices.ABSENT,
        )

    grant = ScopedRoleGrant.objects.create(
        user=user,
        role=RoleChoices.HOD,
        scope_type=ScopeTypeChoices.DEPARTMENT,
        department_id_ref=allowed_department.id,
        valid_from=today,
    )

    request = RequestFactory().get("/reports/")
    request.user = user
    response = attendance_report(request)

    assert response.status_code == 200
    assert "private" in response["Cache-Control"]
    assert "no-store" in response["Cache-Control"]
    assert b"VISIBLE101" in response.content
    assert b"HIDDEN101" not in response.content
    assert b"Download scoped counts" not in response.content

    session_list_request = RequestFactory().get(
        "/reports/sessions/",
        {"start": today.isoformat(), "end": today.isoformat()},
    )
    session_list_request.user = user
    session_list_response = attendance_report_sessions(session_list_request)
    assert session_list_response.status_code == 200
    assert b"VISIBLE101" in session_list_response.content
    assert b"HIDDEN101" not in session_list_response.content

    detail_request = RequestFactory().get(
        f"/reports/sessions/{sessions['A'].id}/"
    )
    detail_request.user = user
    detail_response = attendance_report_session_detail(detail_request, sessions["A"].id)
    assert detail_response.status_code == 200
    assert "private" in detail_response["Cache-Control"]
    assert "no-store" in detail_response["Cache-Control"]
    assert b"Synthetic Student A" in detail_response.content
    assert b"+91" not in detail_response.content

    hidden_detail_request = RequestFactory().get(
        f"/reports/sessions/{sessions['B'].id}/"
    )
    hidden_detail_request.user = user
    with pytest.raises(Http404):
        attendance_report_session_detail(hidden_detail_request, sessions["B"].id)

    export_request = RequestFactory().post(
        "/reports/export/",
        {"start": today.isoformat(), "end": today.isoformat()},
    )
    export_request.user = user
    with pytest.raises(PermissionDenied):
        attendance_report_export(export_request)

    grant.can_export = True
    grant.save(update_fields=["can_export"])
    export_response = attendance_report_export(export_request)

    assert export_response.status_code == 200
    assert export_response["Content-Type"].startswith("text/csv")
    assert b"VISIBLE101" in export_response.content
    assert b"' =HYPERLINK" in export_response.content
    assert b"HIDDEN101" not in export_response.content
    assert b"Synthetic Student" not in export_response.content
    assert AuditEvent.objects.filter(
        actor_user=user,
        action="report.attendance.csv_export",
    ).count() == 1
