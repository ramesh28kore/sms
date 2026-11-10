"""Focused tests for dashboard access behavior."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from datetime import date

from .views import _report_date, attendance_report, dashboard


class DashboardAccessTests(SimpleTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        request = RequestFactory().get("/dashboard/")
        request.user = AnonymousUser()

        response = dashboard(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_anonymous_user_cannot_open_attendance_report(self):
        request = RequestFactory().get("/reports/")
        request.user = AnonymousUser()

        response = attendance_report(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_report_date_rejects_malformed_input(self):
        fallback = date(2026, 11, 1)

        parsed, error = _report_date("not-a-date", fallback)

        self.assertEqual(parsed, fallback)
        self.assertEqual(error, "Enter a valid date.")

    def test_csv_cell_escapes_spreadsheet_formula_prefixes(self):
        from .views import _csv_cell

        self.assertEqual(_csv_cell("=SUM(A1:A2)"), "'=SUM(A1:A2)")
        self.assertEqual(_csv_cell("  =1+1"), "'  =1+1")
        self.assertEqual(_csv_cell("plain text"), "plain text")
