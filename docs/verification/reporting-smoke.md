# Reporting verification evidence

Date: 2026-11-08

## Scope

Verified the reverse-order attendance-report slice with synthetic data only. The report is login-protected, scoped by active grants, date-filtered, grouped by subject and term, and explicitly counts attendance records separately from held sessions. CSV export requires a currently valid grant with `can_export` (or Django superuser), is limited to that export grant's scope, is POST-only, omits student/contact data, protects spreadsheet formula-like text cells, and records an audit event. The report does not infer academic percentages or eligibility.

## Results

| Check | Command / setup | Result |
|---|---|---|
| Python syntax | `python -m py_compile src\apps\reporting\views.py src\apps\reporting\urls.py src\apps\reporting\tests.py src\config\urls.py` | PASS |
| Reporting unit tests | `$env:SECRET_KEY='local-check-only-not-for-production'; $env:DEBUG='true'; $env:POSTGRES_PASSWORD='local-check-only'; .\.venv\Scripts\python.exe -m pytest src\apps\reporting\tests.py -q` | PASS, 4 tests |
| Synthetic report smoke | In-memory SQLite, applied project migrations, created synthetic department/term/student/held session/roster/absent record, invoked `/reports/` with an institute-wide test principal | PASS; route resolved, grouped report rendered the subject, held-session and absent-record counts |
| Department, session-detail, and export-scope regression | `tests/test_reporting_scope.py::test_hod_report_excludes_other_department_sessions`, executed through pytest with an in-memory SQLite override | PASS; the HOD sees only the assigned department's report and sessions, may open an assigned session's roster, receives a non-enumerating 404 for another department's session, and cannot export without `can_export`. An approved scoped export contains no student names and creates an audit event. |
| Complete available suite | `pytest -q` through an isolated Python runner that overrides the test DB to in-memory SQLite | PASS, 16 tests (rerun after session-list/detail changes) |
| Django system check | Same local-only environment, `.\.venv\Scripts\python.exe src\manage.py check` | NOT RUN to completion; startup failed because neither `psycopg` nor `psycopg2` is installed |
| Ruff lint | Pinned Ruff executable | NOT RUN; Ruff is not installed in the current virtual environment |
| PostgreSQL report/permission verification | PostgreSQL service and pinned dependency lock | NOT RUN; not available in this environment |

The local virtual environment uses Django 6.1.3, while `requirements.txt` pins Django 5.2.3. SQLite was used for the tests in this report; neither establishes PostgreSQL locking, query-plan, or production compatibility. The complete suite result is therefore a local logic/smoke result, not production-database evidence.

No live gateway credentials, real student data, or physical SMS were used.

## Session drill-down follow-up

Added a paginated held-session list and a read-only attendance-detail page for the frozen expected roster. The same active scope is applied to both the list and the detail lookup; unauthorized session identifiers return 404. The synthetic regression verifies department isolation and that guardian contact data is not rendered. Syntax compilation, all four reporting unit tests, the scoped regression, and the complete 16-test SQLite suite passed after this change. PostgreSQL and production-database validation remain outstanding.

Authenticated dashboard and report responses now use `Cache-Control: private, no-store`, including the student-level session detail. The HOD scope regression asserts the no-store policy on the report and detail responses. Python compilation and the full available 16-test SQLite suite passed after this change.
