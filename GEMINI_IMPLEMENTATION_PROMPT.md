# Implementation handoff for Gemini Argon

Use the prompt below when starting the implementation model in `D:\1.AVNT\SMS`. This document is a handoff; its creation does not start implementation or authorize live messaging. “Gemini Argon” is the owner's chosen model name, without assumptions about special model capabilities.

---

You are the implementation engineer for **Avanthi Attendance & Parent Alerts**. Build the complete, tested single-institute application described by the local architecture and original product brief. The user/business outcome is accurate faculty attendance and one consolidated daily absence notice per student per designated normalized guardian number, with explainable eligibility, truthful SMS statuses and safe failure recovery.

The tangible deliverable is working source, migrations, locked dependencies, connected responsive screens, a deterministic provider simulator, repeatable tests/CI, sample synthetic data/import files, reproducible deployment configuration, and verified setup/operations documentation. Do not finish at a scaffold or a restatement of the plan.

## Context and references — inspect before editing

1. Read repository AGENTS.md, GEMINI.md, CLAUDE.md, README and dependency/source files if present. Do not invent existing files, architecture or commands; preserve unrelated changes.
2. Read `ARCHITECTURE.md`, `docs/architecture/DATA_MODEL.md`, `docs/architecture/NOTIFICATION_DESIGN.md`, `docs/architecture/VERIFICATION_AND_OPERATIONS.md`, `docs/architecture/SOURCE_REVIEW.md`, `TASKS.md` and `docs/reference/ORIGINAL_PRODUCT_BRIEF.md`.
3. The architecture-only phase found an empty workspace and created documentation, not application code. Inspect again because the workspace may have changed.
4. Treat the original brief as product requirements and the architecture as the implementation design. Follow newer direct owner instructions where they differ. If a material contradiction affects safety or scope, explain it and resolve it before the dependent work; continue independent work.
5. Update `TASKS.md` continuously. Create/update a concise `GEMINI.md` project-memory entry pointing to the architecture and task checklist, with real commands after they exist. If CLAUDE.md is already used, keep its relevant task reference accurate without overwriting unrelated instructions.

## Architecture and non-negotiable requirements

Use the proposed modular Django monolith, PostgreSQL, Django templates/HTMX/Tailwind, Celery/Redis and Linux Docker Compose unless existing suitable source or a demonstrable compatibility issue justifies a documented adjustment. Start with the reviewed Django 5.2 LTS/Python 3.13/PostgreSQL 17/Celery 5.7 baseline, recheck official compatibility, and pin the actual tested dependencies. No unnecessary SPA, microservices, ERP modules or university integration.

Recheck OpenSMS against the recorded commit `810c20de0e512bd0e92094d550a6ddef58a6e286` and record the revision actually targeted. Use a backend adapter, not a fork. Do not invent callbacks, delivery receipts, message IDs, idempotency or health APIs.

Preserve these invariants throughout implementation:

- Effective-dated academic/subject/lab enrollments and frozen session rosters preserve history. Admission batch and current academic year remain distinct.
- Published and sealed expected-session coverage is required; missing generation/marks/registers never mean absence or a completed day.
- Period/session attendance is primary. A multi-period lab has one logical attendance session by default. Daily summaries are unique per student/date and must be current before dispatch.
- FULL_DAY_ABSENT requires at least one held session and all expected sessions resolved/finalized with explicit ABSENT in every held session. PRESENT/LATE/EXCUSED exclude; unresolved work blocks. Alternatives consolidate once with accurate wording/units.
- Academic percentages/thresholds require an approved source and applicable policy. Otherwise show counts and Not configured; zero denominator is N/A. Never invent JNTUH eligibility decisions.
- Permissions combine capability, scope and validity on every backend path, including admin, imports/exports and HTMX. Faculty/HOD isolation, privileged MFA, contact authorization and audit are core functionality.
- Stable daily intent and frozen recipient identity prevent phone/template/schedule changes from creating silent duplicate automatic notices. Siblings remain distinct; duplicate phone links within one student collapse.
- PostgreSQL owns outbox/attempt/notification state. Persist attempt before HTTP; one invocation per attempt, no implicit retry. Redis loss/redelivery must not independently authorize sending.
- Strict `stat=true` means dispatch accepted only. `stat=false`, timeouts and malformed responses do not prove no submission. UNKNOWN never auto-retries; only positively proven pre-submit transient failures can retry within the window.
- Implement the documented lock order, correction boundary, per-gateway serialization/quarantine, shared segment budgets and conservative crash recovery. Do not claim SMS recall or exactly-once physical delivery.
- A fresh sender process generation starts disarmed. Live requires external permission, explicit current-generation administrator activation and all current eligibility checks. Old backups/queues cannot automatically replay messages.
- Development/tests use only the simulator and synthetic data. No live credentials or network access in automated tests. Keep the initial app in SIMULATOR mode.

## Product and interface

Implement all connected screens and onboarding in the architecture: dashboard, students/guardians/imports, session register and daily detail, academic reports, notifications/attempt history, administration/audit. Use the institute identity exactly as supplied, and make unknown institutional facts configurable. Label all demonstration data.

Follow the architecture's concrete typography, spacing, color, table/register layout, mobile behavior and accessibility requirements. Reuse shared components/tokens. Avoid decorative effects that obscure operational information. Distinguish absent students, recipient notices and estimated segments. Show unsaved/conflict/offline/blocked/unknown states honestly; no fake metrics or nonfunctional buttons.

## Scope and autonomy

Proceed autonomously through routine reversible implementation choices, source/dependency inspection, local simulator operation and relevant tests. Build an early end-to-end vertical slice, then complete all phases. Missing hardware, credentials, actual timetable or official academic rules must not prevent a complete simulated application; expose those as clear live-setup requirements.

Do not change unrelated files, introduce unneeded dependencies, buy services, deploy publicly, push protected branches, publish student information or send real SMS. Report unrelated improvement ideas separately. Pause only for destructive real-data changes, a major architecture/scope departure, an externally consumed API change, or a contradiction that prevents a safe authorized implementation. Explain the exact blocker and continue unaffected work. Do not request repeated confirmation for ordinary decisions already within scope.

## Execution and definition of done

Follow P0–P7 in `TASKS.md`. Keep the app runnable after each coherent stage. Mark tasks complete only after implementation and the phase's checks; record failed/unavailable checks accurately. Do not postpone scope-security, temporal constraints or dispatch crash tests until the end.

Completion requires all acceptance cases AC-01–AC-20 and additional safety cases in the verification document to have a recorded result and supporting evidence. Where a physical/institutional check cannot be done locally, distinguish it from implemented simulator behavior and leave live mode disabled. Do not substitute a future-work list for missing core features.

## Verification

Discover or create actual repeatable repository commands; never claim guessed commands ran. Use PostgreSQL and real queue/process boundaries for lock/crash/outage assertions. Count independent simulator-side submissions. Test all dispatch crash windows, queue redelivery/loss, contact/attendance corrections, shared budgets, lock loss, and restoration from a backup predating a same-day accepted send.

Run applicable formatting/lint/type/security/dependency/migration checks, tests, production configuration checks, static assets and container builds. Inspect real browser flows at 360×800, 768×1024 and 1440×900, with keyboard-only usage, 200% zoom and reduced motion. Include error/empty/loading/offline/conflict/unknown states, role-scope attacks and regression checks. Measure the proposed synthetic load profile and disclose the hardware and results. Simulator tests do not establish physical SIM delivery.

Create the actual setup, backup/restore, upgrade/rollback and runbook commands matching the delivered service names, execute the safe synthetic procedures, and retain evidence. Document the separate controlled physical test for an authorized operator to run later.

## Final handoff

Update TASKS.md and provide a concise report: completed functionality and file locations; exact verified startup commands; checks run with results/evidence; failed/unavailable checks and limitations; any remaining decisions; and the operator inputs needed for real use. State the active mode and that no physical delivery was proved unless a separately authorized hardware test actually occurred. Do not claim perfection, production certification or guaranteed delivery.

Begin with a brief implementation sequence and any material assumptions, then start P0. Continue through implementation within the authorized scope rather than stopping after another plan.
