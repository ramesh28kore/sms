# Claude Code prompt: Avanthi B.Tech attendance and absence SMS application

Act as a senior full-stack engineer responsible for implementing, testing, and documenting a reliable B.Tech attendance web application for Avanthi Institute of Engineering and Technology, under JNTUH as specified by the project owner. Build the working application in the current workspace. Do not stop at a proposal, architecture diagram, mockup, or scaffold.

## 1. Product objective and scope

Create a polished, responsive web application that sends a daily SMS only to the designated parents/guardians of B.Tech students whose finalized attendance meets the institute's approved absence-notification rule for that date. Support faculty attendance entry by subject and period, including laboratory groups, and consolidate results into at most one automatic daily absence notice per student per designated parent number.

Use the product title "Avanthi Attendance & Parent Alerts" and the full institute name "Avanthi Institute of Engineering and Technology". Display "B.Tech | JNTUH" as the configured academic context. The institution name and affiliation are project-owner inputs, not independently certified facts. Do not invent a campus address, college code, logo, department list, official contacts, accreditation, or university integration. Make those administrator-configurable and label example data clearly. Use a neutral text-based identity until approved brand assets are supplied.

Use https://github.com/daslearning-org/OpenSMS as the SMS gateway. Build the attendance management, recipient selection, scheduling, notification tracking, and administrative interface around it. OpenSMS is an external service running on an Android phone with a SIM, or a supported computer/modem setup; it is not the attendance database.

Deliver a complete application for this institute first. Exclude fees, admissions, examination results, unrelated college ERP modules, biometrics, facial recognition, parent accounts, marketing campaigns, and multi-tenant SaaS unless the existing project already requires them. Avoid unnecessary microservices. Do not connect to or scrape JNTUH systems without an explicitly authorized integration.

Read the existing project's README, CLAUDE.md, AGENTS.md, dependency files, and relevant source before editing. Preserve unrelated work. If an existing architecture is suitable, extend it. Otherwise use a supported Django release, PostgreSQL, Django templates with HTMX and Tailwind CSS, Celery, and Redis. Keep durable notification state in PostgreSQL, not only in Redis. Use Docker Compose for reproducible local operation. Verify current APIs and dependency versions against official documentation and pin dependencies.

Before implementing, inspect the current OpenSMS README and sending code, record the commit reviewed, and document the actual capabilities and limitations. Prefer an adapter around upstream OpenSMS over maintaining a fork.

## 2. Working approach and configuration

First present a concise implementation plan and assumptions, then proceed with implementation. Resolve ordinary technical choices independently. Ask only for genuinely blocking requirements. Missing credentials or physical SMS hardware must not prevent completion of the application using a realistic simulator.

Make these settings configurable: institute name and campus identifier, official contact, timezone, academic year, admission batch, academic regulation identifier, departments/branches, study year, semester, sections, lab groups, subject offerings, timetable, instructional days, holidays, attendance cutoff, notification time, latest allowed sending time, absence-notification rule, gateway connection, recipient policy, message template, and sending limits. Default the B.Tech structure to years I-IV with semesters I/II within each year, while preserving data-driven configuration for approved variations, lateral entry, transfers, and readmission.

Default the institute timezone to Asia/Kolkata and phone-number parsing region to India (+91), with administrator confirmation before live use and support for valid international guardian numbers. Store dates/times correctly and display student-facing dates unambiguously. Do not hard-code an SMS allowance, carrier policy, legal requirement, or sending capacity. The actual timetable and SMS sending time are not yet supplied; use labeled demo values and require configuration before live sending.

Keep the daily absence-SMS policy separate from academic attendance-percentage rules. JNTUH-related thresholds, denominator rules, condonation, exemptions, regulation codes, and exam eligibility must not be guessed. Associate any academic reporting policy with its applicable batch/regulation, effective dates, and an institute-approved source. If no authoritative rule is supplied, show descriptive counts only and label academic thresholds "Not configured". Do not label a student detained or exam-ineligible automatically. These academic rules are not a prerequisite for building or simulating the daily parent-alert workflow.

Start in SIMULATOR mode. Production SMS remains disabled until an administrator configures the real gateway and explicitly enables live sending. Do not send real messages during development, automated testing, or unattended verification. Do not deploy publicly, purchase services, push to protected branches, or publish student information as part of implementation.

## 3. Roles and access

Implement server-enforced permissions:

- Institute administrator: manage academic configuration, users, students, guardians, schedules, templates, gateway configuration, notifications, and audit history.
- Principal or authorized academic management: view institute-wide summaries and reports; operational write privileges must be explicitly granted.
- Head of Department (HOD): review attendance, finalization gaps, corrections, and reports within the assigned department.
- Faculty member: access assigned subject/section/period or lab-group sessions, mark attendance, finalize those sessions, and see permitted results.
- Class in-charge or mentor: review assigned sections, identify incomplete session registers, and review daily absence summaries and parent alerts within their scope.
- Attendance officer: review institute-wide attendance, manage permitted corrections, inspect blocked notifications, and handle authorized operational exceptions.

Restrict exports, contact reveals, live-mode activation, gateway secrets, schedule changes, and manual resends appropriately. Faculty must not access unassigned sections, subjects, or lab groups by changing a URL, form value, or API identifier. HOD access must remain department-scoped. Model substitutions and temporary faculty assignments with validity dates. Hide unauthorized controls, but enforce permissions independently on every backend operation. Do not add public registration or shared default production credentials.

## 4. Data model and imports

Model InstituteSettings, Department, Programme, AdmissionBatch, AcademicRegulation, AcademicYear, Semester, ClassSection, LabGroup, Subject, SubjectOffering, FacultyAssignment, TimetableSlot, Student, Enrollment, SubjectEnrollment, Guardian, StudentGuardianLink, AttendanceSession, AttendanceRecord, DailyAttendanceSummary, AcademicCalendarDay, AcademicAttendancePolicy, NotificationPolicy, MessageTemplate, Notification, DeliveryAttempt, OutboxEvent, and AuditEvent, or equivalent maintainable models.

Use stable IDs and database constraints. Preserve historical department/branch, year, semester, section, lab-group and subject enrollment, attendance, template versions, and the recipient/message snapshot used for each sending attempt. Separate admission batch from current academic year so lateral-entry, readmitted, and transferred students retain accurate history. Distinguish a guardian relationship from a phone number; siblings can share a guardian. Default to one designated guardian per student, with an explicit option to notify multiple designated guardians. Deduplicate identical normalized phone numbers for the same student and notification.

Support manual student management and CSV import/export. Provide sample columns for hall_ticket_number, student_name, admission_batch, academic_regulation, department_code, branch_code, study_year, semester, section, lab_group, guardian_name, guardian_relationship, guardian_phone, notification_preference, and enrollment_status. Optional values must have documented defaults rather than silently invented data. Keep an internal stable student ID and treat hall-ticket/roll numbers as strings. Validate hall-ticket formats through configurable rules, not a guessed JNTUH regex. Never match students by name alone.

Provide import preview with column mapping, row-level errors, duplicate detection, reference-data checks, and explicit create/update behavior. Include a separate attendance import format keyed by date, session/subject, and hall-ticket number; imported attendance remains draft until an authorized faculty member finalizes it. Treat phone numbers as strings, preserve leading characters, and normalize to E.164 using a maintained library and the configured region. Quarantine missing or invalid numbers rather than silently guessing.

Imports must be transactional, repeatable, size-limited, and authorization-checked. Escape spreadsheet-formula payloads in exports. Keep archived/inactive students out of future attendance and notification selection while retaining authorized history. B.Tech students may be adults; do not assume that every parent's number is automatically an authorized disclosure recipient. Record the institute-approved student/guardian contact authorization and notification preferences, with review and opt-out handling under the applicable institutional policy, without claiming that these records alone establish legal compliance.

## 5. Attendance workflow and exact eligibility rules

Faculty select the academic year, branch, study year/semester, section, subject, scheduled period/session, and institute-local date, load the appropriate enrolled roster, mark attendance, save a draft, review totals, and explicitly finalize the session register. Lab sessions use the correct lab-group roster. Provide search by hall-ticket number/name, keyboard-friendly entry, clear save indicators, and a confirmation before bulk marking. Do not silently default everybody to present or absent.

Support UNMARKED, PRESENT, ABSENT, LATE, and EXCUSED; record approved leave/on-duty reasons separately where needed. UNMARKED must never mean ABSENT. Finalization must reject unresolved UNMARKED entries for students expected in that session, with a clear explanation. Distinguish a cancelled/not-conducted session from a conducted session with missing attendance.

Use subject/period attendance as the primary source and derive one daily summary per student/date. Enforce unique AttendanceRecord(student_id, attendance_session_id) and DailyAttendanceSummary(student_id, institute_local_date). Do not impose uniqueness on student/date for raw period attendance. Handle approved extra classes, faculty substitutions, timetable changes, student-specific electives, and labs spanning several periods without duplicating attendance credit or daily alerts. Preserve the effective timetable/session roster and auditable changes for historical dates.

The safe default notification rule is FULL_DAY_ABSENT: send only when at least one session was actually held for the student that day, all expected non-cancelled sessions have been resolved and all conducted sessions finalized, and every conducted session is explicitly ABSENT. Any PRESENT or LATE session excludes the student from a full-day absence notice. An EXCUSED session also excludes the student under this default; missing/unfinalized sessions block classification. A day with no held sessions must never create an absence notice.

The institute may explicitly choose an alternative rule: ANY_SESSION_ABSENT or ABSENT_SESSION_THRESHOLD. Configure its threshold, session-counting basis, approved-excuse treatment, and notification wording. Even for these rules, send one consolidated daily notice after the day's required attendance is complete. A student absent for one lecture must not receive wording that claims full-day absence. The live-mode setup must show the selected rule for administrator confirmation. Do not infer a policy from JNTUH affiliation.

Eligibility requires all of the following:

- The date is an active instructional day and matches the intended institute-local sending date.
- The student has an active enrollment for that date.
- All expected sessions affecting this student's daily decision have been resolved and all conducted-session registers finalized.
- The latest daily summary qualifies under the explicitly selected absence-notification rule.
- The configured notification time has arrived and the sending window is still open.
- At least one designated, eligible guardian has a valid phone number.
- Notification preferences, pause controls, and configured sending limits allow dispatch.
- No equivalent notification has already been accepted by the gateway or remains unresolved after a potentially successful dispatch.

Evaluate students/sections with complete required attendance independently; one unfinished section or unrelated elective must not block the entire institute. Show missing subject/period registers prominently to the responsible faculty and class in-charge. If the required sessions are finalized after the scheduled time but within the sending window, process the daily summary on the next scheduler pass. After the window expires, flag it for review rather than silently sending late or next-day messages. Configure sending after the actual final instructional period, not an invented morning cutoff.

Require an audit reason and appropriate role authorization for changes to finalized attendance. Recompute the daily summary after session, roster, cancellation, or attendance corrections and cancel pending notifications when eligibility no longer holds. Recheck eligibility immediately before dispatch. If a change arrives after dispatch has begun, show that cancellation is no longer guaranteed. Never claim to retract an SMS. Correction messages must be a distinct, explicit, audited action, disabled by default.

Provide subject-wise and semester attendance counts with transparent denominators and drill-down to underlying sessions. If an institution-approved academic policy is configured, calculate percentages using its session/period weighting, held-versus-scheduled basis, lab duration, exemptions, and effective enrollment dates. Otherwise show counts without invented official percentages or compliance labels. Zero held sessions must display "N/A", never zero percent or full attendance. Keep low-attendance alerts and exam-eligibility decisions outside automatic daily absence SMS scope.

## 6. OpenSMS adapter and truthful status reporting

Verify the upstream contract before coding. At the time of this brief, relevant source files are:

- https://github.com/daslearning-org/OpenSMS/blob/main/README.md
- https://github.com/daslearning-org/OpenSMS/blob/main/app/services/postApi.py
- https://github.com/daslearning-org/OpenSMS/blob/main/app/services/smsApi.py

The documented request is POST /sms/ with an Authorization: Bearer API_KEY header and JSON containing number and text. The default port is 9292. The reviewed implementation returns a JSON stat boolean; the Android path calls SmsManager without delivery callbacks.

Implement a backend-only provider interface with an OpenSMS adapter and a deterministic simulator. Keep API keys out of browser JavaScript, public endpoints, source control, screenshots, and logs. Prefer deployment secrets or a protected server-side secret store; do not store plaintext gateway keys in ordinary editable settings.

Handle authentication errors, invalid numbers, connection errors, timeouts, HTTP errors, malformed responses, stat=false, and stat=true distinctly. Validate the response body; HTTP 200 by itself is not success. Treat stat=true as gateway dispatch accepted, not recipient delivery confirmed. The reviewed Android implementation does not establish carrier acceptance or handset delivery. Do not invent delivery receipts, message IDs, callbacks, bulk APIs, idempotency keys, or health endpoints that upstream does not provide.

Use explicit statuses such as Blocked, Queued, Dispatching, Dispatch accepted, Failed, Unknown outcome, Cancelled, and Expired. Reserve Delivered for a future provider with genuine delivery evidence. Distinguish current contact information from the historical destination snapshot.

Provide non-sending connection diagnostics with honest limitations. Any test SMS must require an authorized user's explicit action, display the destination and message, and count toward limits. A cloud server cannot automatically reach a phone on campus Wi-Fi; implement and document a workable network topology.

## 7. Scheduling, duplicate prevention, and failure recovery

Implement durable background execution with a single normal scheduler, periodic reconciliation, PostgreSQL-backed notification state, and a transactional outbox or equivalent design that survives broker outages. Multiple workers, duplicate tasks, double clicks, scheduler restarts, and repeated daily scans must not create independent sends for the same intended notification.

Persist timestamps in UTC and evaluate calendar rules in the institute's configured IANA timezone. Derive attendance dates consistently. Handle holidays, weekends, schedule changes, DST in supported timezones, restarts, and expired work. Do not replay historical absence notifications automatically after an outage. A manual historical send must show its original date and require an authorized reason.

Enforce a database uniqueness rule for the business notification, covering institute, student, attendance date, normalized recipient, and notification kind. Separate delivery attempts from notification identity. Attendance edits, template edits, schedule changes, phone changes, and repeated task publication must not silently create a new send for an already processed daily notification. Preserve enough stable identity to enforce that rule when contact details change.

Use database transactions and atomic claims or row locks to prevent concurrent dispatch. Persist the attempt before making the external request. Serialize access to each OpenSMS gateway and enforce configurable pacing and daily SMS-segment budgets shared across workers.

Critically, do not claim exactly-once physical SMS delivery. A timeout or worker crash after a request may mean the phone already sent the message. Upstream has no confirmed idempotency or reconciliation API. Therefore:

- Automatically retry only failures that can reliably be classified as occurring before possible dispatch; bound retries and use backoff with jitter.
- Treat ambiguous read timeouts, connection loss after submission, malformed success responses, uncertain provider failures, and stale in-flight attempts as Unknown outcome.
- Never blindly retry Unknown outcome or Dispatch accepted.
- Recover stale worker claims conservatively; lease expiry alone does not prove a message was not sent.
- Offer a restricted manual resend with a duplicate-risk explanation, explicit reason, and separate audit record.

Define the state machine, transitions, transaction boundaries, crash windows, and cancellation race in documentation and tests. Configure task retry/redelivery behavior so it cannot bypass these rules. Check pause controls and eligibility again before beginning each external call. Provide a global emergency stop and per-gateway pause; already submitted messages cannot be recalled.

## 8. Templates and message budgets

Provide a versioned, administrator-editable template with an allowlist of placeholders, such as student_name, hall_ticket_number, branch_code, study_year, semester, section, attendance_date, absent_sessions, held_sessions, institute_name, approved_short_name, and institute_contact. Escape output correctly and do not evaluate arbitrary template code. Select templates by notification policy so a partial-day absence cannot use a full-day template.

Default FULL_DAY_ABSENT example: "Dear Parent, {student_name} ({hall_ticket_number}), {branch_code} Year {study_year}, was marked absent for all held classes on {attendance_date}. Contact {institute_contact} if incorrect. - {approved_short_name}"

Alternative partial-day example: "Dear Parent, {student_name} ({hall_ticket_number}) was marked absent for {absent_sessions} of {held_sessions} held sessions on {attendance_date}. Contact {institute_contact}. - {approved_short_name}"

Default the editable short name to "Avanthi Institute" and preview it for administrator approval. This text signature does not configure or imply a registered telecom sender ID; OpenSMS uses the configured SIM. Provide English and editable Telugu templates with accurate segment estimates. Treat translations as drafts for institutional review before live activation. Keep session counts consistent with the actual configured session-counting basis.

Show a realistic preview and an estimated GSM-7/Unicode multipart segment count, including GSM extension characters and Unicode/non-BMP edge cases. Label estimates honestly. Long or regional-language messages may use multiple SMS segments. Configure limits in segments, not only number of API requests. Do not hard-code carrier prices or advertise free/unlimited SMS.

Provide editable wording for supported languages, missing-placeholder validation, a maximum length/segment policy, and a preview of intended recipients before an authorized manual batch. Record the actual rendered text used, accessible only to permitted users. Do not include sensitive student information beyond what the attendance notice needs.

## 9. Web interface and usability

Deliver real, connected screens for:

- Dashboard: today's attendance totals by department/branch/year/semester/section, unfinished subject registers, eligible recipients, accepted dispatches, blocked/failed/unknown notifications, gateway connectivity limitations, and next scheduled run.
- Students and guardians: hall-ticket/name search, academic filters, profile editing, enrollment history, contact authorization and validation, import preview, and authorized exports.
- Attendance: a fast mobile-friendly subject/period/lab register, draft/finalized state, daily aggregation details, corrections, and history.
- Academic reports: subject-wise and semester session counts, policy-backed percentages when configured, date-range filters, underlying-record drill-down, and authorized CSV export. Do not brand these as official JNTUH submissions.
- Notifications: date/department/branch/section/status filters, selected rule and reason for inclusion or blocking, recipient masking, attempt history, failure explanations, and permitted review actions.
- Administration: departments, academic batches/regulations, semesters, subjects, sections, lab groups, timetables, faculty assignments, academic calendar, notification schedules, templates, mode controls, limits, gateway configuration, and audit history.

Make dashboard metrics explicit: student absence counts, guardian notification counts, and SMS-segment estimates are different quantities. Never label dispatch acceptance as delivery.

Use clear typography, consistent spacing, accessible contrast, visible keyboard focus, associated labels, useful error messages, confirmation for consequential actions, and proper empty/loading/offline states. Target WCAG 2.2 AA and verify core keyboard workflows. Work well on phones and desktops. Show timezone and date clearly. Handle concurrent attendance edits with conflict detection rather than silently overwriting another faculty member's changes. No fake metrics or nonfunctional buttons in the finished app.

## 10. Security and student data protection

Use established authentication and authorization mechanisms, secure sessions, CSRF protection, production HTTPS, safe password reset, login throttling, password policies, and a documented administrator account recovery process. Include administrator MFA using a maintained package if compatible with the chosen stack. Apply least privilege and avoid exposing student contact data to unauthorized staff.

Validate inputs, use parameterized ORM queries, escape output, constrain uploads, protect exports, and set appropriate security headers. Protect against IDOR, XSS, CSRF, SQL injection, session abuse, and SSRF. Gateway addresses must be administrator-controlled and restricted to explicitly approved hosts/ports; private LAN addresses are legitimate here, so use an allowlist rather than a blanket private-address prohibition. Reject unexpected redirects and access to metadata endpoints.

Keep OpenSMS on a trusted isolated LAN or secured private tunnel; do not expose its HTTP port directly to the internet. Protect the connection appropriately when crossing untrusted networks. Production setup must distinguish the web application's HTTPS endpoint from the private gateway endpoint.

Implement restricted audit events for attendance changes, finalization, contact changes, imports, permissions, schedule/template changes, mode activation, dispatch attempts, and manual resends. Redact secrets, phone numbers, and message content from ordinary infrastructure logs. Protect database files, backup storage, encryption keys, and exports. Make retention and deletion policies configurable with documented audit implications. Do not claim legal compliance from a checklist; document what the institute must confirm for its country and carrier before live operation.

## 11. Deployment, operation, and recovery

Provide Dockerfiles, a Compose setup, environment examples without secrets, migrations, demo seeding, health/readiness checks for the application services, persistent volumes, and documented startup commands. Do not expose PostgreSQL or Redis publicly. Keep development and production settings separate. Pin and lock dependencies; include applicable upstream license notices.

Document a recommended campus-LAN deployment, Android SIM/SMS permission setup, keeping the gateway reachable and powered, reserving its LAN address, and diagnosing Android background restrictions. Document cloud deployment only with an explicit secure path to the gateway. Do not imply hosting the web application alone supplies SMS capability.

Provide structured logs, queue-age monitoring, worker/scheduler heartbeat, gateway-error visibility, daily dispatch summaries, and in-app operational alerts. Monitoring must never send a real SMS merely to check health.

Include backup and restore commands, encryption/key-handling guidance, a restore exercise, upgrade and rollback procedures, and database migration cautions. After a restore, keep live sending disabled until notification history and ambiguous in-flight attempts are reconciled; an old database backup must not cause already-sent messages to be replayed. Treat the database as authoritative and reconcile broker tasks against its state.

Include an operations runbook for phone offline, missing SIM allowance, rejected SMS permission, invalid credentials, unfinished attendance, queue backlog, ambiguous outcome, database/broker outage, accidental absence entry, and emergency pause. State practical capacity limits based on configuration and measured tests, not unsupported throughput claims.

## 12. Testing and acceptance criteria

Use realistic synthetic data only. All automatic SMS tests must use the simulator. Exercise the real database and queue behavior where correctness depends on them. Include unit, integration, concurrency, security, and browser tests for the relevant behaviors, rather than tests that merely mirror implementation.

At minimum prove:

1. Under FULL_DAY_ABSENT, a student marked ABSENT in every finalized held session, with all expected sessions resolved and an eligible guardian, generates one daily notification.
2. Under FULL_DAY_ABSENT, any PRESENT, LATE, EXCUSED, or UNMARKED session, unfinished register, inactive enrollment, wrong date, or no-held-session day prevents the full-day absence notification.
3. Missing/invalid contacts and disabled preferences are blocked with useful reasons.
4. Weekends, holidays, timezones, DST, late finalization, and expired sending windows behave as documented.
5. Duplicate scheduler runs, concurrent workers, repeated tasks, double clicks, and repeated imports do not create duplicate dispatches.
6. Attendance corrections cancel pending work; after-dispatch corrections are reported honestly.
7. Phone/template/schedule changes do not cause silent re-sending of completed daily notifications.
8. HTTP 200 with stat=false is not success; stat=true is never displayed as confirmed delivery.
9. Timeout after possible submission and crashes around the external call become Unknown outcome without automatic duplicate-producing retries.
10. Authentication failure, malformed responses, gateway offline, broker/database outages, and service restarts recover safely.
11. Role restrictions and object-level access hold for every sensitive view, action, and export.
12. Segment budgeting, Unicode messages, per-gateway serialization, emergency pause, and dry-run/live separation work across workers.
13. Backup restoration does not automatically replay sent notifications.
14. The complete browser workflow works: administrator configures the Avanthi academic structure, creates a student/guardian, enrolls the student in subjects, builds the timetable, and assigns faculty; faculty finalize period/lab attendance; the daily summary resolves; the scheduler processes one eligible parent notification; the simulator records it; authorized staff see the correct result and audit history.
15. Partial attendance, electives, lab subgroups, multi-period labs, cancelled classes, extra classes, timetable revisions, and substitutions do not falsely classify students as absent for the entire day.
16. Alternative absence rules produce one consolidated daily notice with truthful partial-day wording, not a message per absent period.
17. HOD access remains department-scoped; faculty access remains subject/section/session-scoped; temporary assignments expire correctly.
18. Hall-ticket import, lateral entry, section changes, readmission, academic-regulation history, and student-specific enrollment preserve correct historical attendance.
19. Academic percentage reports have transparent denominators, handle zero held sessions as N/A, follow only explicitly configured academic rules, and do not invent JNTUH eligibility decisions.
20. Shared parent numbers across siblings, duplicate guardian links, contact-authorization changes, and international numbers are handled without collapsing different students' notices or duplicating one student's notice.

Run formatter/linter checks, relevant type checks, tests, dependency/security checks supported by the environment, production configuration checks, and the production build. Inspect key screens at mobile and desktop sizes. Fix discovered problems and rerun affected checks. Report commands and results accurately, including checks you could not execute. Simulator tests do not prove physical SIM delivery; provide a separate controlled live-test procedure for the institute to run later.

## 13. Deliverables and definition of done

Deliver working source code, migrations, locked dependencies, the provider simulator, realistic demo seed data, sample import files, automated tests, CI configuration, deployment files, and concise setup/user/operations documentation.

Include an architecture overview, schema explanation, notification state machine, API contract, threat-model notes, and a requirement-to-test checklist. Document intentional limitations and any incomplete acceptance criteria. Provide a first-run wizard that guides the administrator through institute identity/campus and contact settings, academic structure, actual department list, timetable, student/guardian import, faculty assignments, guardian contact authorization, selected daily absence rule, finalization and sending times, templates, simulator verification, gateway configuration, and explicit live-mode activation. Separately show academic reporting policy as unconfigured until an approved source and applicable batch/regulation are provided.

Implement in coherent stages: project foundation and permissions; roster/imports and attendance; OpenSMS adapter and simulator; durable scheduling and dispatch; polished UI and operations; verification and documentation. Keep the application runnable throughout. Do not leave placeholders in core functionality or substitute a long future-work list for implementation.

Finish with a concise report stating what was built, where the files are, how to start it, what was tested, remaining limitations, and exactly which operator inputs are needed for live use. Never claim the system is perfect, production-certified, or capable of guaranteed SMS delivery. Demonstrate that the requested workflow works and clearly identify the hardware and operational checks still required.

Begin by inspecting the workspace and upstream OpenSMS, then implement the application.
