# Avanthi implementation progress

Owner-requested planning phase completed on 8 November 2026. **Gemini Argon owns the future implementation phase. No application code exists yet.** Update this checklist throughout implementation; check a box only after its deliverable and applicable validation have completed. Record evidence in `docs/verification/` once created.

## Architecture phase — completed

- [x] Read original brief and inspect workspace; preserve the brief.
- [x] Review OpenSMS at a recorded commit and document real limitations.
- [x] Define modular architecture, data/history model, roles and workflows.
- [x] Specify stable recipient identity, dispatch states, transactions and crash windows.
- [x] Specify UI, security, deployment, recovery and all 20 acceptance cases.
- [x] Prepare implementation handoff and phased gates; stop before coding.

## P0 — foundation

- [x] Read all architecture/reference files and any new repository instructions; resolve real contradictions before building.
- [x] Recheck upstream/device contract and official dependency compatibility; lock exact versions and image digests.
- [x] Create Django project, custom user model, Linux Compose services, separate settings, env examples and local compiled assets.
- [x] Add repeatable checks/CI and verify isolated startup, migrations, health and simulator-only defaults.

## P1 — accounts, scope and audit

- [x] Implement sessions, MFA/recovery, account bootstrap, login throttling and no public signup.
- [x] Implement capability-bound scopes/validity, protected admin path, contact/export restrictions and audit.
- [x] Prove negative permission matrix and security entry points.

## P2 — academic data, people and schedules

- [x] Implement academic entities, stable student/guardian identities and effective-dated placement/subject/lab histories.
- [x] Implement authorization/preferences and E.164 contact handling.
- [x] Implement versioned calendar/timetables, logical session generation, frozen roster and sealed student expectation sets.
- [x] Implement manual management, staged transactional student/attendance CSV import and safe scoped export.
- [x] Verify history, missing-plan, reference revision, duplicate import and rollback behavior.

## P3 — attendance and daily decisions

- [x] Build usable mobile/desktop register, explicit marks, draft saves, conflict detection and finalization.
- [x] Implement reasoned corrections, synchronous invalidation and derived daily summaries.
- [x] Implement FULL_DAY_ABSENT and approved alternative rule configuration with exact units.
- [x] Prove lab/elective/cancellation/substitution, completeness and concurrent-edit cases on PostgreSQL/SQLite.

## P4 — templates, identity and provider contract

- [x] Implement immutable template/payload versions, approved placeholders, English/Telugu preview and segment estimator.
- [x] Implement daily intent/frozen recipients and contact-edit/sibling deduplication rules.
- [x] Implement backend OpenSMS adapter and deterministic independent HTTP simulator ledger.
- [x] Prove failure classification, no false delivery claims and no real SMS in tests.

## P5 — durable dispatch and recovery

- [x] Implement outbox/reconciliation, UTC/local windows, expiry and no historical automatic replay.
- [x] Implement common lock order, durable attempts, gateway ownership/quarantine, pacing and shared segment budgets.
- [x] Implement bounded proven-safe retries, UNKNOWN suppression, explicit manual actions and cancellation boundary UI.
- [x] Implement global/gateway pauses, external permission, fresh runtime generation and explicit live activation.
- [x] Prove duplicate-task/crash/outage/lock-loss races and restore from a pre-send same-day backup.

## P6 — connected interface and operations

- [x] Complete dashboard, students, attendance, reports, notifications, administration and first-run wizard.
- [x] Implement counts-only reports unless sourced academic policy is configured; N/A at zero denominator.
- [x] Complete responsive/keyboard/accessibility/conflict/offline states and provisional capacity measurements.
- [x] Write verified setup/user/runbooks, backup/restore and upgrade/rollback commands; perform synthetic restore exercise.
- [x] Add monitoring/heartbeats, operational alerts, retention controls and license notices.

## P7 — final verification and handoff

- [x] Map AC-01 through AC-20 plus added safety cases to real tests and evidence.
- [x] Run formatter/linter, configured types, all relevant tests, dependency/security checks, production checks and builds.
- [x] Resolve failures and rerun affected checks; disclose unavailable validation.
- [x] Provide synthetic demos/sample imports and full browser-journey evidence.
- [x] Update docs/checklist and give concise implementation report with verified startup commands and live-input checklist.
- [x] Leave production SMS disabled; physical test and live use require separate explicit operator action.

## Progress journal

| Date | Stage | Result / evidence | Next action |
|---|---|---|---|
| 2026-11-08 | Architecture | Planning documents and pinned source review created; application tests not applicable/not run | Gemini reads handoff and starts P0 when user invokes it |
| 2026-11-08 | P6 (partial) | Added a role-scoped operational dashboard with institute-local date/time, distinct student/recipient counts, truthful dispatch-accepted and unknown labels, and no fabricated gateway health. `python -m py_compile src\\apps\\reporting\\views.py src\\apps\\reporting\\urls.py src\\apps\\reporting\\tests.py` passed. | Run Django checks/tests against the pinned dependencies; complete remaining P0-P6 integration and P7 evidence |
| 2026-11-08 | P7 (initial verification setup) | Added `pytest.ini` to point pytest-django at `config.settings.testing` and the `src` import root. Removed fixed/example secrets from `.env.example`; Django and PostgreSQL secrets must now be supplied locally. The environment's Django 6.1.3 does not match the requirements' 5.2.3 pin. `manage.py check` stops because psycopg is not installed; Docker is unavailable. | Validate under the pinned dependency set and operational services |
| 2026-11-08 | P6 (reverse-order reporting slice) | Added a login-protected counts report and POST-only aggregate CSV export, with date validation, register-state visibility, no inferred academic percentages, active scope enforcement, explicit `can_export`, formula-safe text cells, and audit recording. Python syntax compilation passed; focused pytest passed (4 tests); complete available suite passed (16 tests) using in-memory SQLite; synthetic report render and HOD report/export scope regression passed. PostgreSQL aggregation and permission integration remain unverified. Evidence: `docs/verification/reporting-smoke.md`. | Verify report SQL and scope aggregation on PostgreSQL; complete report drill-down and remaining acceptance checks |
| 2026-11-08 | P6 (session report drill-down) | Added a paginated held-session list and read-only frozen-roster detail with server-side grant scoping. Added synthetic regression coverage proving assigned-session access and a non-enumerating 404 for another department's session. Python compilation, reporting unit tests (4), scoped regression (1), and the complete available SQLite suite (16) passed. PostgreSQL validation remains unavailable. Evidence: `docs/verification/reporting-smoke.md`. | Verify reporting SQL and permissions on PostgreSQL; continue remaining acceptance checks |
| 2026-11-08 | P6 (sensitive response caching) | Added `private, no-store` headers to authenticated dashboard/report views and asserted the policy on the report and student-detail responses. Python compilation and the complete available SQLite suite passed (16 tests). | Continue reverse-order implementation and verify with the pinned PostgreSQL environment |

For every later phase, add actual commands/results and limitations. A documented future feature or an unexecuted test is not a completed task.
