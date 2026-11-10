"""Forms for student & guardian CRUD."""
import phonenumbers
from django import forms
from django.conf import settings

from apps.academics.models import AdmissionBatch, ClassSection
from apps.people.models import Student


class StudentForm(forms.Form):
    """
    Combined form for a student, their designated guardian contact,
    and optional class-section enrollment (needed to appear in attendance).
    Mirrors the CSV bulk-import validation rules.
    """
    hall_ticket_number = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. 23A91A0501"}),
    )
    full_name = forms.CharField(
        max_length=255, label="Student name",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}),
    )
    is_active = forms.BooleanField(required=False, initial=True)
    section = forms.ModelChoiceField(
        queryset=ClassSection.objects.filter(is_active=True).select_related("term", "term__branch"),
        required=False,
        label="Class section (for attendance)",
        widget=forms.Select(attrs={"class": "form-input"}),
        help_text="Enroll the student so they appear in attendance registers.",
    )
    admission_batch = forms.ModelChoiceField(
        queryset=AdmissionBatch.objects.filter(is_active=True),
        required=False,
        label="Admission batch",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    guardian_name = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Rajesh Sharma"}),
    )
    guardian_relationship = forms.CharField(
        max_length=64, required=False, initial="Parent",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Father / Mother / Guardian"}),
    )
    guardian_phone = forms.CharField(
        max_length=32, required=False, label="Guardian phone",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "10-digit mobile, e.g. 9848012345"}),
    )

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student

    def clean_hall_ticket_number(self):
        htn = self.cleaned_data["hall_ticket_number"].strip()
        qs = Student.objects.filter(hall_ticket_number=htn)
        if self.student:
            qs = qs.exclude(pk=self.student.pk)
        if qs.exists():
            raise forms.ValidationError("A student with this hall ticket number already exists.")
        return htn

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("section") and not cleaned.get("admission_batch"):
            self.add_error("admission_batch", "Select the admission batch when enrolling in a section.")
        return cleaned

    def clean_guardian_phone(self):
        phone = self.cleaned_data.get("guardian_phone", "").strip()
        if not phone:
            return ""
        region = getattr(settings, "PHONE_REGION", "IN")
        try:
            parsed = phonenumbers.parse(phone, region)
        except phonenumbers.NumberParseException as exc:
            raise forms.ValidationError(f"Not a valid phone number: {exc}.")
        if not phonenumbers.is_valid_number(parsed):
            raise forms.ValidationError("This phone number does not look valid for the configured region.")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

