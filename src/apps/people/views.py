import csv
import io
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.accounts.permissions import is_admin, has_role
from apps.accounts.models import RoleChoices
from apps.people.models import Student, Guardian, GuardianContact, StudentGuardianLink, Enrollment
from apps.academics.models import ClassSection, TeachingTerm, AdmissionBatch


@login_required
def student_list_view(request):
    query = request.GET.get("q", "").strip()
    students = Student.objects.all().select_related()
    if query:
        students = students.filter(hall_ticket_number__icontains=query) | students.filter(full_name__icontains=query)

    can_reveal = is_admin(request.user) or request.user.role_grants.filter(can_reveal_contacts=True, is_active=True).exists()

    return render(request, "students/list.html", {
        "students": students[:100],
        "query": query,
        "can_reveal_contacts": can_reveal,
    })


@login_required
def student_detail_view(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    links = student.guardian_links.all().select_related("guardian", "contact")
    enrollments = student.enrollments.all().select_related("term", "section", "admission_batch")

    can_reveal = is_admin(request.user) or request.user.role_grants.filter(can_reveal_contacts=True, is_active=True).exists()

    return render(request, "students/detail.html", {
        "student": student,
        "links": links,
        "enrollments": enrollments,
        "can_reveal_contacts": can_reveal,
    })


@login_required
def export_students_csv(request):
    if not (is_admin(request.user) or request.user.role_grants.filter(can_export=True, is_active=True).exists()):
        raise PermissionDenied("You do not have permission to export student data.")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="students_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "hall_ticket_number", "student_name", "batch", "term", "section", "guardian_name", "guardian_phone"
    ])

    for s in Student.objects.all().prefetch_related("enrollments", "guardian_links"):
        enroll = s.enrollments.first()
        link = s.guardian_links.filter(is_designated_recipient=True).first()
        
        # Prevent spreadsheet formula injection
        htn = f"'{s.hall_ticket_number}" if s.hall_ticket_number.startswith(("=", "+", "-", "@")) else s.hall_ticket_number
        name = f"'{s.full_name}" if s.full_name.startswith(("=", "+", "-", "@")) else s.full_name
        phone = str(link.contact.normalized_number) if link and link.contact else ""

        writer.writerow([
            htn, name,
            enroll.admission_batch.code if enroll else "",
            str(enroll.term) if enroll else "",
            enroll.section.section_code if enroll else "",
            link.guardian.full_name if link else "",
            phone
        ])

    return response

