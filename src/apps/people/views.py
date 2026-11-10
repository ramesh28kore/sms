import csv
import io
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.accounts.permissions import is_admin, has_role
from apps.accounts.models import RoleChoices
from apps.people.forms import StudentForm
from apps.people.models import (
    Student, Guardian, GuardianContact, StudentGuardianLink, Enrollment,
    ContactStatusChoices, NotificationPreferenceChoices,
)
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


def _save_student_and_guardian(form: StudentForm, student: Student | None, user):
    """
    Persist the combined student + designated guardian contact form.
    On edit, a changed phone creates a NEW GuardianContact (contacts may be
    shared between siblings), and a changed guardian name creates a new
    Guardian if the existing one is linked to other students.
    Returns (student, created).
    """
    data = form.cleaned_data
    created = student is None
    with transaction.atomic():
        if created:
            student = Student(
                hall_ticket_number=data["hall_ticket_number"],
                created_by=user,
            )
        student.full_name = data["full_name"]
        student.date_of_birth = data["date_of_birth"]
        student.is_active = data["is_active"]
        if not created:
            student.hall_ticket_number = data["hall_ticket_number"]
        student.save()

        gname = data["guardian_name"].strip() or f"Guardian of {student.full_name}"
        rel = data["guardian_relationship"].strip() or "Parent"
        phone = data["guardian_phone"]  # already E.164-normalized or ""

        link = student.guardian_links.filter(is_designated_recipient=True).first()
        guardian = link.guardian if link else None

        if guardian is None:
            guardian = Guardian.objects.create(full_name=gname, relationship_default=rel)
        elif guardian.full_name != gname:
            if guardian.student_links.exclude(student=student).exists():
                guardian = Guardian.objects.create(full_name=gname, relationship_default=rel)
                if link:
                    link.guardian = guardian
            else:
                guardian.full_name = gname
                guardian.relationship_default = rel
                guardian.save()

        contact = link.contact if link else None
        if contact is None or str(contact.normalized_number or "") != phone:
            contact = GuardianContact.objects.create(
                guardian=guardian,
                raw_number=phone or "NONE",
                normalized_number=phone or None,
                status=ContactStatusChoices.ACTIVE if phone else ContactStatusChoices.INVALID,
            )

        if link is None:
            StudentGuardianLink.objects.create(
                student=student,
                guardian=guardian,
                contact=contact,
                relationship=rel,
                is_designated_recipient=True,
                notification_preference=NotificationPreferenceChoices.ENABLED,
            )
        else:
            link.contact = contact
            link.relationship = rel
            link.save()
    return student, created


@login_required
def student_create_view(request):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can add students.")

    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            student, _ = _save_student_and_guardian(form, None, request.user)
            messages.success(request, f"Student {student} added.")
            return redirect("people:detail", student_id=student.id)
    else:
        form = StudentForm()

    return render(request, "students/form.html", {"form": form, "is_edit": False})


@login_required
def student_update_view(request, student_id):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can edit students.")

    student = get_object_or_404(Student, id=student_id)
    link = student.guardian_links.filter(is_designated_recipient=True).select_related("guardian", "contact").first()

    if request.method == "POST":
        form = StudentForm(request.POST, student=student)
        if form.is_valid():
            _save_student_and_guardian(form, student, request.user)
            messages.success(request, f"Student {student} updated.")
            return redirect("people:detail", student_id=student.id)
    else:
        form = StudentForm(
            student=student,
            initial={
                "hall_ticket_number": student.hall_ticket_number,
                "full_name": student.full_name,
                "date_of_birth": student.date_of_birth,
                "is_active": student.is_active,
                "guardian_name": link.guardian.full_name if link else "",
                "guardian_relationship": link.relationship if link else "Parent",
                "guardian_phone": str(link.contact.normalized_number) if link and link.contact and link.contact.normalized_number else "",
            },
        )

    return render(request, "students/form.html", {"form": form, "is_edit": True, "student": student})


@login_required
def student_delete_view(request, student_id):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can delete students.")

    student = get_object_or_404(Student, id=student_id)

    if request.method == "POST":
        try:
            with transaction.atomic():
                student.delete()
            messages.success(request, f"Student {student.hall_ticket_number} — {student.full_name} deleted.")
        except ProtectedError:
            # Attendance/enrollment history exists; archive instead of deleting.
            student.is_active = False
            student.archived_at = timezone.now()
            student.archived_reason = "Archived via staff portal (has academic history; hard delete blocked)."
            student.save()
            messages.warning(
                request,
                f"{student.full_name} has attendance/enrollment history, so they were archived instead of deleted.",
            )
        return redirect("people:list")

    return render(request, "students/confirm_delete.html", {"student": student})


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

