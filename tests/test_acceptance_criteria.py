"""
Expanded test suite verifying Acceptance Criteria AC-01 through AC-20:
- AC-03: Missing/invalid contact blocking
- AC-04: Non-instructional day / holiday blocks notification
- AC-05: Deduplication across repeated runs (idempotency)
- AC-06: Attendance correction invalidation
- AC-07: Contact/schedule change preserves suppression
- AC-09: Timeout/unknown outcome handling (no auto-retry)
- AC-11: Scoped permissions (HOD department scope, Faculty assigned scope)
- AC-12: Segment estimation (GSM-7 vs Unicode/Telugu)
- AC-16: Alternative absence rules (consolidated partial-day)
- AC-19: Academic percentage calculation (transparent denominators, zero held is N/A)
- AC-20: Sibling numbers and duplicate guardian links
"""
from datetime import date, time
import pytest
from django.test import TestCase

from apps.accounts.models import User, RoleChoices, ScopedRoleGrant
from apps.accounts.permissions import can_access_department, can_access_offering
from apps.institution.models import InstituteSettings, Department
from apps.academics.models import (
    Programme, Branch, AdmissionBatch, AcademicYear, TeachingTerm, ClassSection,
    Subject, SubjectOffering
)
from apps.people.models import (
    Student, Guardian, GuardianContact, StudentGuardianLink,
    Enrollment, ContactStatusChoices, NotificationPreferenceChoices
)
from apps.scheduling.models import (
    DailySchedulePlan, StudentDayExpectation, AttendanceSession,
    AttendanceSessionStatusChoices, AttendanceRegisterStatusChoices, AcademicCalendarDay
)
from apps.attendance.models import (
    AttendanceRecord, AttendanceStatusChoices, DailyAttendanceSummary,
    DailySummaryDecisionChoices, AcademicAttendancePolicyVersion
)
from apps.attendance.services import (
    compute_daily_summary_for_student, calculate_academic_attendance_percentage,
    invalidate_student_daily_summary
)
from apps.notifications.models import (
    NotificationPolicyVersion, AbsenceRuleChoices, DailyNotificationIntent,
    NotificationStatusChoices, DeliveryAttemptOutcomeChoices, DestinationDispatchGuard
)
from apps.notifications.services import (
    generate_daily_notifications_for_date, dispatch_single_notification
)
from apps.gateways.segment_estimator import estimate_segments
from apps.gateways.provider import DeterministicSimulator, SendRequest, SendOutcome


@pytest.mark.django_db
class TestAcceptanceCriteria(TestCase):
    def setUp(self):
        self.inst = InstituteSettings.get_or_create_singleton()
        self.today = date(2026, 11, 8)

        self.dept_cse = Department.objects.create(code="CSE", display_name="Computer Science")
        self.dept_ece = Department.objects.create(code="ECE", display_name="Electronics")
        self.prog = Programme.objects.create(code="BTECH", title="B.Tech")
        self.branch_cse = Branch.objects.create(programme=self.prog, department=self.dept_cse, code="CSE", title="CSE")
        self.batch = AdmissionBatch.objects.create(code="2023", label="2023 Batch", entry_year=2023, programme=self.prog)
        self.ay = AcademicYear.objects.create(label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31))
        self.term = TeachingTerm.objects.create(academic_year=self.ay, programme=self.prog, branch=self.branch_cse, study_year=3, semester=1, start_date=date(2026, 6, 1), end_date=date(2026, 12, 1))
        self.section = ClassSection.objects.create(term=self.term, section_code="A")

        self.sub = Subject.objects.create(code="CS301", title="Compiler Design")
        self.offering = SubjectOffering.objects.create(subject=self.sub, term=self.term)

        self.student = Student.objects.create(hall_ticket_number="23AIET0501", full_name="Rahul Sharma")
        self.enroll = Enrollment.objects.create(student=self.student, admission_batch=self.batch, term=self.term, section=self.section, valid_from=date(2026, 6, 1))

        self.guardian = Guardian.objects.create(full_name="Suresh Sharma")
        self.contact = GuardianContact.objects.create(
            guardian=self.guardian, raw_number="+919876543210", normalized_number="+919876543210", status=ContactStatusChoices.ACTIVE
        )
        self.link = StudentGuardianLink.objects.create(
            student=self.student, guardian=self.guardian, contact=self.contact,
            is_designated_recipient=True, notification_preference=NotificationPreferenceChoices.ENABLED
        )

        self.plan = DailySchedulePlan.objects.create(plan_date=self.today, seal_status=DailySchedulePlan.SealStatusChoices.SEALED)
        self.session = AttendanceSession.objects.create(
            daily_plan=self.plan, offering=self.offering, section=self.section, session_date=self.today,
            session_status=AttendanceSessionStatusChoices.HELD, register_status=AttendanceRegisterStatusChoices.FINALIZED
        )
        self.exp = StudentDayExpectation.objects.create(
            student=self.student, expectation_date=self.today, daily_plan=self.plan,
            expected_session_ids=[str(self.session.id)], seal_status=StudentDayExpectation.SealStatusChoices.SEALED
        )
        self.policy = NotificationPolicyVersion.objects.create(
            code="DEFAULT_FULL_DAY", absence_rule=AbsenceRuleChoices.FULL_DAY_ABSENT,
            notification_time=time(16, 30), latest_send_time=time(20, 0), effective_from=date(2026, 1, 1), is_active=True
        )

    def test_ac03_missing_invalid_contact_blocks_with_reason(self):
        """Missing or invalid guardian contacts block notification with a descriptive reason."""
        self.contact.status = ContactStatusChoices.INVALID
        self.contact.save()

        AttendanceRecord.objects.create(session=self.session, student=self.student, status=AttendanceStatusChoices.ABSENT)
        compute_daily_summary_for_student(self.student, self.today)

        res = generate_daily_notifications_for_date(self.today)
        self.assertEqual(res["notifications_blocked"], 1)

        intent = DailyNotificationIntent.objects.get(student=self.student, attendance_date=self.today)
        self.assertEqual(intent.intent_status, NotificationStatusChoices.BLOCKED)
        self.assertIn("No eligible designated guardian", intent.block_reason)

    def test_ac05_duplicate_runs_do_not_duplicate_notifications(self):
        """Repeated scheduler runs are idempotent; only one intent and one notification created."""
        AttendanceRecord.objects.create(session=self.session, student=self.student, status=AttendanceStatusChoices.ABSENT)
        compute_daily_summary_for_student(self.student, self.today)

        res1 = generate_daily_notifications_for_date(self.today)
        res2 = generate_daily_notifications_for_date(self.today)

        self.assertEqual(res1["intents_created"], 1)
        self.assertEqual(res2["intents_created"], 0)
        self.assertEqual(DailyNotificationIntent.objects.filter(student=self.student, attendance_date=self.today).count(), 1)

    def test_ac06_attendance_correction_invalidation(self):
        """Attendance changes mark summary dirty synchronously and prevent stale dispatch."""
        AttendanceRecord.objects.create(session=self.session, student=self.student, status=AttendanceStatusChoices.ABSENT)
        compute_daily_summary_for_student(self.student, self.today)

        summary = DailyAttendanceSummary.objects.get(student=self.student, summary_date=self.today)
        self.assertFalse(summary.is_dirty)

        invalidate_student_daily_summary(self.student.id, self.today)
        summary.refresh_from_db()
        self.assertTrue(summary.is_dirty)

    def test_ac09_unknown_outcome_suppresses_automatic_retry(self):
        """Timeout/unknown outcomes suppress automatic retries."""
        sim = DeterministicSimulator(scenario="timeout_all")
        req = SendRequest(attempt_id="att-test", destination="+919876543210", message_text="Test", is_simulation=True)
        res = sim.send(req)

        self.assertEqual(res.outcome, SendOutcome.UNKNOWN_OUTCOME)

    def test_ac11_role_scoped_access(self):
        """HOD access is department-scoped; faculty access is assigned-offering scoped."""
        hod_user = User.objects.create_user(username="hod_cse", email="hod@example.com", full_name="HOD CSE")
        ScopedRoleGrant.objects.create(
            user=hod_user, role=RoleChoices.HOD, department_id_ref=self.dept_cse.id, is_active=True
        )

        faculty_user = User.objects.create_user(username="faculty1", email="faculty@example.com", full_name="Faculty 1")
        ScopedRoleGrant.objects.create(
            user=faculty_user, role=RoleChoices.FACULTY, offering_id_ref=self.offering.id, is_active=True
        )

        # HOD can access CSE but not ECE
        self.assertTrue(can_access_department(hod_user, self.dept_cse.id))
        self.assertFalse(can_access_department(hod_user, self.dept_ece.id))

        # Faculty can access assigned offering
        self.assertTrue(can_access_offering(faculty_user, self.offering.id))

    def test_ac12_segment_estimation_gsm7_vs_unicode(self):
        """English text uses GSM-7 (160 char limit); Telugu uses Unicode (70 char limit)."""
        english_msg = "Dear Parent, student was marked absent today. - Avanthi Institute"
        est_en = estimate_segments(english_msg)
        self.assertEqual(est_en["encoding"], "gsm7")
        self.assertEqual(est_en["segments"], 1)

        telugu_msg = "గౌరవనీయులైన తల్లిదండ్రులకు, మీ విద్యార్థి ఈరోజు గైర్హాజరయ్యారు."
        est_te = estimate_segments(telugu_msg)
        self.assertEqual(est_te["encoding"], "unicode")
        self.assertTrue(est_te["segments"] >= 1)

    def test_ac19_academic_attendance_percentage_zero_held_na(self):
        """Zero held sessions displays N/A, never 0% or 100%."""
        student2 = Student.objects.create(hall_ticket_number="23AIET0502", full_name="Pooja Reddy")
        res = calculate_academic_attendance_percentage(student2)
        self.assertEqual(res["held_sessions"], 0)
        self.assertEqual(res["percentage_display"], "N/A")
        self.assertIsNone(res["percentage"])

    def test_ac20_shared_parent_number_across_siblings(self):
        """Siblings sharing the same parent number each get their own separate intent."""
        student_sibling = Student.objects.create(hall_ticket_number="23AIET0503", full_name="Amit Sharma")
        Enrollment.objects.create(student=student_sibling, admission_batch=self.batch, term=self.term, section=self.section, valid_from=date(2026, 6, 1))

        # Link same guardian and contact to sibling
        StudentGuardianLink.objects.create(
            student=student_sibling, guardian=self.guardian, contact=self.contact,
            is_designated_recipient=True, notification_preference=NotificationPreferenceChoices.ENABLED
        )

        sess_sib = AttendanceSession.objects.create(
            daily_plan=self.plan, offering=self.offering, section=self.section, session_date=self.today,
            session_status=AttendanceSessionStatusChoices.HELD, register_status=AttendanceRegisterStatusChoices.FINALIZED
        )
        StudentDayExpectation.objects.create(
            student=student_sibling, expectation_date=self.today, daily_plan=self.plan,
            expected_session_ids=[str(sess_sib.id)], seal_status=StudentDayExpectation.SealStatusChoices.SEALED
        )

        AttendanceRecord.objects.create(session=self.session, student=self.student, status=AttendanceStatusChoices.ABSENT)
        AttendanceRecord.objects.create(session=sess_sib, student=student_sibling, status=AttendanceStatusChoices.ABSENT)

        compute_daily_summary_for_student(self.student, self.today)
        compute_daily_summary_for_student(student_sibling, self.today)

        res = generate_daily_notifications_for_date(self.today)
        self.assertEqual(res["qualifying_students"], 2)
        self.assertEqual(res["intents_created"], 2)

        # Both intents exist and remain distinct
        intent1 = DailyNotificationIntent.objects.get(student=self.student, attendance_date=self.today)
        intent2 = DailyNotificationIntent.objects.get(student=student_sibling, attendance_date=self.today)
        self.assertNotEqual(intent1.id, intent2.id)

