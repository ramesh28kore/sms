import csv
import hashlib
import io
import phonenumbers
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_admin
from apps.imports_export.models import ImportJob, ImportJobStatusChoices, ImportJobTypeChoices, ImportRow
from apps.people.models import (
    Student, Guardian, GuardianContact, StudentGuardianLink, Enrollment,
    ContactStatusChoices, NotificationPreferenceChoices, EnrollmentStatusChoices
)
from apps.institution.models import Department
from apps.academics.models import (
    AdmissionBatch, AcademicRegulation, Branch, TeachingTerm, ClassSection,
    Subject, SubjectOffering
)
from apps.scheduling.models import AttendanceSession, AttendanceRegisterStatusChoices
from apps.attendance.models import AttendanceRecord, AttendanceStatusChoices


@login_required
def import_upload_view(request):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can import CSV data.")

    if request.method == "POST":
        import_type = request.POST.get("import_type", ImportJobTypeChoices.STUDENTS)
        csv_file = request.FILES.get("csv_file")

        if not csv_file:
            return render(request, "imports/upload.html", {"error": "Please select a valid CSV file."})

        # Read content and compute hash
        content = csv_file.read()
        file_hash = hashlib.sha256(content).hexdigest()

        # Parse CSV
        decoded_file = content.decode("utf-8-sig", errors="replace")
        csv_reader = csv.DictReader(io.StringIO(decoded_file))

        job = ImportJob.objects.create(
            import_type=import_type,
            status=ImportJobStatusChoices.PREVIEW_READY,
            original_filename=csv_file.name,
            file_hash=file_hash,
            uploaded_by=request.user,
        )

        row_num = 1
        valid_count = 0
        error_count = 0

        for row in csv_reader:
            errors = []
            warnings = []
            row_dict = dict(row)

            if import_type == ImportJobTypeChoices.STUDENTS:
                htn = row_dict.get("hall_ticket_number", "").strip()
                name = row_dict.get("student_name", "").strip()
                phone = row_dict.get("guardian_phone", "").strip()

                if not htn:
                    errors.append("Missing hall_ticket_number.")
                if not name:
                    errors.append("Missing student_name.")

                # Phone validation
                if phone:
                    try:
                        parsed = phonenumbers.parse(phone, "IN")
                        if not phonenumbers.is_valid_number(parsed):
                            warnings.append(f"Phone {phone} may be invalid; will be quarantined.")
                    except Exception as e:
                        warnings.append(f"Phone format error: {str(e)}; will be quarantined.")
                else:
                    warnings.append("No guardian phone provided.")

            elif import_type == ImportJobTypeChoices.ATTENDANCE:
                session_id = row_dict.get("session_id", "").strip()
                htn = row_dict.get("hall_ticket_number", "").strip()
                status = row_dict.get("status", "").strip().lower()

                if not session_id:
                    errors.append("Missing session_id.")
                if not htn:
                    errors.append("Missing hall_ticket_number.")
                if status not in [c.value for c in AttendanceStatusChoices]:
                    errors.append(f"Invalid attendance status: '{status}'.")

            status = ImportRow.RowStatusChoices.ERROR if errors else (
                ImportRow.RowStatusChoices.WARNING if warnings else ImportRow.RowStatusChoices.VALID
            )

            if errors:
                error_count += 1
            else:
                valid_count += 1

            ImportRow.objects.create(
                job=job,
                row_number=row_num,
                raw_data=row_dict,
                errors=errors,
                warnings=warnings,
                status=status,
            )
            row_num += 1

        job.total_rows = row_num - 1
        job.valid_rows = valid_count
        job.error_rows = error_count
        job.save()

        return redirect("imports_export:preview", job_id=job.id)

    return render(request, "imports/upload.html")


@login_required
def import_preview_view(request, job_id):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can review imports.")

    job = get_object_or_404(ImportJob, id=job_id)
    rows = job.rows.all().order_by("row_number")[:100]

    return render(request, "imports/preview.html", {
        "job": job,
        "rows": rows,
    })


@login_required
def import_commit_view(request, job_id):
    if not is_admin(request.user):
        raise PermissionDenied("Only administrators can commit imports.")

    job = get_object_or_404(ImportJob, id=job_id)

    if job.status == ImportJobStatusChoices.COMMITTED:
        return redirect("imports_export:preview", job_id=job.id)

    if request.method == "POST":
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for row in job.rows.filter(status__in=[ImportRow.RowStatusChoices.VALID, ImportRow.RowStatusChoices.WARNING]):
                data = row.raw_data

                if job.import_type == ImportJobTypeChoices.STUDENTS:
                    htn = data.get("hall_ticket_number", "").strip()
                    name = data.get("student_name", "").strip()
                    gname = data.get("guardian_name", "").strip() or f"Guardian of {name}"
                    rel = data.get("guardian_relationship", "Parent").strip()
                    phone = data.get("guardian_phone", "").strip()

                    student, s_created = Student.objects.get_or_create(
                        hall_ticket_number=htn,
                        defaults={"full_name": name}
                    )
                    if s_created:
                        created_count += 1
                    else:
                        student.full_name = name
                        student.save()
                        updated_count += 1

                    # Guardian & Contact
                    guardian, _ = Guardian.objects.get_or_create(full_name=gname)
                    normalized_str = None
                    c_status = ContactStatusChoices.INVALID

                    if phone:
                        try:
                            parsed = phonenumbers.parse(phone, "IN")
                            if phonenumbers.is_valid_number(parsed):
                                normalized_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                                c_status = ContactStatusChoices.ACTIVE
                        except Exception:
                            c_status = ContactStatusChoices.INVALID

                    contact, _ = GuardianContact.objects.get_or_create(
                        guardian=guardian,
                        raw_number=phone or "NONE",
                        defaults={
                            "normalized_number": normalized_str,
                            "status": c_status,
                        }
                    )

                    StudentGuardianLink.objects.get_or_create(
                        student=student,
                        guardian=guardian,
                        contact=contact,
                        defaults={
                            "relationship": rel,
                            "is_designated_recipient": True,
                            "notification_preference": NotificationPreferenceChoices.ENABLED,
                        }
                    )

                elif job.import_type == ImportJobTypeChoices.ATTENDANCE:
                    session_id = data.get("session_id", "").strip()
                    htn = data.get("hall_ticket_number", "").strip()
                    status_val = data.get("status", "").strip().lower()

                    session = AttendanceSession.objects.filter(id=session_id).first()
                    student = Student.objects.filter(hall_ticket_number=htn).first()

                    if session and student:
                        record, r_created = AttendanceRecord.objects.get_or_create(
                            session=session,
                            student=student,
                            defaults={"status": status_val, "last_updated_by": request.user}
                        )
                        if not r_created:
                            record.status = status_val
                            record.last_updated_by = request.user
                            record.save()
                            updated_count += 1
                        else:
                            created_count += 1

                row.status = ImportRow.RowStatusChoices.COMMITTED
                row.save()

            job.status = ImportJobStatusChoices.COMMITTED
            job.created_count = created_count
            job.updated_count = updated_count
            job.committed_at = timezone.now()
            job.save()

        return redirect("imports_export:preview", job_id=job.id)

    return redirect("imports_export:preview", job_id=job.id)
