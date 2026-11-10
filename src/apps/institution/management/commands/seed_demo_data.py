from datetime import date, time
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User, RoleChoices, ScopedRoleGrant, ScopeTypeChoices
from apps.institution.models import InstituteSettings, Department
from apps.academics.models import (
    Programme, Branch, AdmissionBatch, AcademicYear, TeachingTerm, ClassSection,
    Subject, SubjectOffering, FacultyAssignment
)
from apps.people.models import (
    Student, Guardian, GuardianContact, StudentGuardianLink, Enrollment,
    ContactStatusChoices, NotificationPreferenceChoices
)
from apps.scheduling.models import (
    DailySchedulePlan, StudentDayExpectation, AttendanceSession,
    AttendanceSessionStatusChoices, AttendanceRegisterStatusChoices
)
from apps.attendance.models import (
    AttendanceRecord, AttendanceStatusChoices, AcademicAttendancePolicyVersion
)
from apps.notifications.models import (
    NotificationPolicyVersion, AbsenceRuleChoices, MessageTemplateVersion
)
from apps.gateways.models import GatewayConfig


class Command(BaseCommand):
    help = "Seed realistic synthetic demo data for Avanthi Institute."

    def handle(self, *args, **options):
        self.stdout.write("Seeding synthetic data for Avanthi Institute of Engineering and Technology...")

        # 1. Institute Settings
        inst = InstituteSettings.get_or_create_singleton()
        inst.institute_name = "Avanthi Institute of Engineering and Technology"
        inst.approved_short_name = "Avanthi Institute"
        inst.academic_context_label = "B.Tech | JNTUH"
        inst.official_contact = "+91 891 281 2345"
        inst.timezone = "Asia/Kolkata"
        inst.phone_region = "IN"
        inst.sms_mode = "simulator"
        inst.save()

        # 2. Departments
        cse_dept, _ = Department.objects.get_or_create(code="CSE", defaults={"display_name": "Computer Science & Engineering"})
        ece_dept, _ = Department.objects.get_or_create(code="ECE", defaults={"display_name": "Electronics & Communication Engineering"})

        # 3. Programme & Branch
        btech, _ = Programme.objects.get_or_create(code="BTECH", defaults={"title": "Bachelor of Technology", "duration_years": 4})
        branch_cse, _ = Branch.objects.get_or_create(programme=btech, department=cse_dept, code="CSE", defaults={"title": "Computer Science & Engineering"})

        # 4. Academic Year & Term
        ay, _ = AcademicYear.objects.get_or_create(label="2026-27", defaults={"start_date": date(2026, 6, 1), "end_date": date(2027, 5, 31), "is_current": True})
        batch_2023, _ = AdmissionBatch.objects.get_or_create(code="2023", defaults={"label": "2023 Cohort", "entry_year": 2023, "programme": btech})
        term_y3s1, _ = TeachingTerm.objects.get_or_create(academic_year=ay, programme=btech, branch=branch_cse, study_year=3, semester=1, defaults={"start_date": date(2026, 6, 1), "end_date": date(2026, 12, 1)})
        sec_a, _ = ClassSection.objects.get_or_create(term=term_y3s1, section_code="A")

        # 5. Subjects & Offerings
        sub_os, _ = Subject.objects.get_or_create(code="CS301", defaults={"title": "Operating Systems"})
        sub_cn, _ = Subject.objects.get_or_create(code="CS302", defaults={"title": "Computer Networks"})
        off_os, _ = SubjectOffering.objects.get_or_create(subject=sub_os, term=term_y3s1)
        off_cn, _ = SubjectOffering.objects.get_or_create(subject=sub_cn, term=term_y3s1)

        # 6. Faculty
        faculty_user, _ = User.objects.get_or_create(username="faculty_rao", defaults={"email": "rao.faculty@avanthi.edu.in", "full_name": "Dr. K. V. Rao", "is_staff": True})
        faculty_user.set_password("FacultyPass123!")
        faculty_user.save()
        ScopedRoleGrant.objects.get_or_create(
            user=faculty_user,
            role=RoleChoices.FACULTY,
            offering_id_ref=off_os.id,
            defaults={"scope_type": ScopeTypeChoices.OFFERING},
        )

        # 7. Students & Guardians
        students_data = [
            ("23AIET0501", "K. Sai Kumar", "K. Rama Rao", "+919848022338"),
            ("23AIET0502", "P. Ananya Reddy", "P. Venkat Reddy", "+919849011223"),
            ("23AIET0503", "B. Teja Varun", "B. Mohan Rao", "+919988776655"),
            ("23AIET0504", "V. Harika", "V. Satyanarayana", "+919123456789"),
        ]

        created_students = []
        for htn, sname, gname, phone in students_data:
            s, _ = Student.objects.get_or_create(hall_ticket_number=htn, defaults={"full_name": sname})
            Enrollment.objects.get_or_create(student=s, admission_batch=batch_2023, term=term_y3s1, section=sec_a, defaults={"valid_from": date(2026, 6, 1)})
            g, _ = Guardian.objects.get_or_create(full_name=gname)
            c, _ = GuardianContact.objects.get_or_create(guardian=g, raw_number=phone, defaults={"normalized_number": phone, "status": ContactStatusChoices.ACTIVE})
            StudentGuardianLink.objects.get_or_create(student=s, guardian=g, contact=c, defaults={"is_designated_recipient": True, "relationship": "Parent"})
            created_students.append(s)

        # 8. Today's Plan & Sessions
        today = timezone.localdate()
        plan, _ = DailySchedulePlan.objects.get_or_create(plan_date=today, defaults={"seal_status": DailySchedulePlan.SealStatusChoices.SEALED})
        sess1, _ = AttendanceSession.objects.get_or_create(daily_plan=plan, offering=off_os, section=sec_a, session_date=today, defaults={"session_status": AttendanceSessionStatusChoices.HELD, "register_status": AttendanceRegisterStatusChoices.FINALIZED})
        sess2, _ = AttendanceSession.objects.get_or_create(daily_plan=plan, offering=off_cn, section=sec_a, session_date=today, defaults={"session_status": AttendanceSessionStatusChoices.HELD, "register_status": AttendanceRegisterStatusChoices.FINALIZED})

        for s in created_students:
            StudentDayExpectation.objects.get_or_create(student=s, expectation_date=today, daily_plan=plan, defaults={"expected_session_ids": [str(sess1.id), str(sess2.id)], "seal_status": StudentDayExpectation.SealStatusChoices.SEALED})

        # Mark first student Absent in both (triggering daily absence)
        AttendanceRecord.objects.get_or_create(session=sess1, student=created_students[0], defaults={"status": AttendanceStatusChoices.ABSENT})
        AttendanceRecord.objects.get_or_create(session=sess2, student=created_students[0], defaults={"status": AttendanceStatusChoices.ABSENT})

        # Mark others Present
        for s in created_students[1:]:
            AttendanceRecord.objects.get_or_create(session=sess1, student=s, defaults={"status": AttendanceStatusChoices.PRESENT})
            AttendanceRecord.objects.get_or_create(session=sess2, student=s, defaults={"status": AttendanceStatusChoices.PRESENT})

        # 9. Notification Policy & Template
        NotificationPolicyVersion.objects.get_or_create(
            code="FULL_DAY_DEFAULT",
            defaults={
                "absence_rule": AbsenceRuleChoices.FULL_DAY_ABSENT,
                "notification_time": time(16, 30),
                "latest_send_time": time(20, 0),
                "effective_from": date(2026, 1, 1),
                "is_active": True,
            }
        )

        MessageTemplateVersion.objects.get_or_create(
            code="FULL_DAY_EN",
            version_number=1,
            language="en",
            defaults={
                "template_text": "Dear Parent, {student_name} ({hall_ticket_number}), {branch_code} Year {study_year}, was marked absent for all held classes on {attendance_date}. Contact {institute_contact} if incorrect. - {approved_short_name}",
                "is_approved": True,
            }
        )

        # 10. Gateway Simulator
        GatewayConfig.objects.get_or_create(
            name="Default Simulator",
            defaults={"host": "127.0.0.1", "port": 9292, "is_simulator": True, "is_active": True}
        )

        self.stdout.write(self.style.SUCCESS("Demo seed data created successfully!"))

