# Security, deployment, verification and handoff gates

This document defines required implementation evidence. **No application tests, deployment checks or physical SMS tests have been run during the architecture-only phase.** The acceptance IDs below are planned tests, not passing results.

## 1. Security boundaries

| Threat | Required control | Proof |
|---|---|---|
| Faculty/HOD accesses another scope by changing IDs | Central capability + scope + validity checks on reads and mutations, including related object IDs | Negative permission matrix for views, HTMX, imports, exports and background actions |
| Administrator MFA bypass | Custom user from first migration, allauth TOTP/recovery codes, protected/disabled independent Django admin login | Login through every exposed entry point; recovery/session-revocation tests |
| Forged/replayed actions or overwrites | CSRF, POST-only mutations, bound request tokens, optimistic revisions and transactional services | Cross-origin rejection; double-click and concurrent-save tests |
| Secret/PII leakage | Secret references, restrictive logs, masked contacts, no public exports, restricted messages/audit | Capture logs/errors/HTML/queue payloads and check forbidden values |
| SSRF through gateway configuration | Explicit host/scheme/port allowlist, pinned approved address resolution, no redirects/proxy inheritance, dispatcher egress restriction | Reject metadata/link-local/loopback where not approved, alternate IP notation, rebinding and redirect fixtures |
| Wrong guardian disclosure | Per-student contact authorization/purpose, opt-out, current recheck and frozen snapshots | Authorization revoked between queue and call; siblings and changed phone tests |
| Malicious CSV or template | Upload limits, CSV-only processing, formula-safe exports, literal placeholder allowlist | Oversized/invalid encoding/duplicate rows/formula injection/template-expression fixtures |
| Duplicate sends after failure/restore | Durable intent/attempt ledger, conservative UNKNOWN, external live arm and generation | Process crash, redelivery and old-backup replay tests |
| Silent audit/history tampering | Append-only application audit, separate migration/admin DB credentials, controlled retention | Normal app role cannot edit/delete protected events/history |

Use TLS for web access; secure HttpOnly session cookies, appropriate SameSite, host/origin validation, session expiry, password policy, login throttling and generic password-reset responses. Disable public account creation and unnecessary social authentication. Institute administrator is a scoped application role; reserve Django superuser for controlled break-glass maintenance.

Require recent MFA for live activation, gateway/permission changes, manual resends and sensitive exports. Store recovery codes securely using the maintained package. Provide an audited local administrator recovery process; if email transport is not configured, do not present a password-reset flow that claims an email was sent. Recovery revokes affected sessions and does not reveal gateway secrets.

Use parameterized ORM operations, escaped templates, a tested CSP and safe security headers. Configure HTMX to avoid evaluating unnecessary inline code, exclude untrusted `hx-*` attributes, and disable sensitive history snapshots. Assets are pinned and served locally. Validate security controls against the actual chosen package versions rather than weakening CSP silently to make a widget work.

No request bodies, full phone numbers, rendered SMS text, bearer tokens, imported rows or reset/MFA secrets in ordinary logs or analytics. Use opaque IDs, status/reason codes, durations and correlation IDs. Store restricted audit diffs and attempt message snapshots behind explicit permission. OpenSMS itself logs phone numbers in the reviewed implementation; contain its logs on the managed gateway with restricted access/retention and exclude them from broad log shipping. The app cannot claim to redact a third-party device's logs by changing its own logging configuration.

Protect persistent disks/backups and separate encryption keys from the backup archive. Decide configurable retention periods with the institute; no invented statutory duration. Deletion/redaction is a privileged workflow with explicit traceability consequences. Keep necessary deduplication/suppression evidence for any retained automatic sending window. Institutional authorization records and these controls are not a legal-compliance certification; the institute confirms applicable country/carrier and disclosure requirements before live operation.

## 2. Deployment topology

Recommended first production target is a maintained campus Linux host with reliable LAN, SSD storage, backup destination, UPS and an assigned operator. Windows workspace development uses Linux containers/WSL2; do not plan native Windows Celery workers. Compose provides reproducibility, not high availability.

| Service | Exposure / persistence |
|---|---|
| HTTPS reverse proxy | Staff-accessible HTTPS endpoint; trusted certificate even on campus LAN |
| Django web | Private container network; production server, DEBUG off |
| General Celery worker | Private; imports/projections/outbox/reconciliation; no gateway secret/egress |
| Dedicated sender | Private; one normal consumer per gateway; uniquely allowed gateway secret and network path |
| Celery beat | One normal scheduler; monitored heartbeat; duplicated wake-ups remain safe |
| PostgreSQL | Private only; persistent data volume; separate application and migration roles |
| Redis | Private only; credentials as appropriate; broker recoverable from database state |
| Simulator | Development/test profile; private only; independent submission evidence storage |
| Backup job/storage | Encrypted, access-restricted, retained separately from the host |

The application image is shared between roles, but runtime secrets/network permissions are not. Do not publish PostgreSQL/Redis ports on public interfaces. Production media/imports/exports are outside public static roots. Keep development and production settings separate; prevent demo credentials/seeds from initializing operational deployments. Environment examples contain placeholders only.

Phone setup: approved OpenSMS installation and recorded version/build, SMS permission, selected SIM, verified allowance, powered device, reserved LAN address and reachable trusted network. Document Android sleep/background restrictions and device restart handling. Do not instruct broad disabling of device security as a routine setup step; any installation restrictions require the institute's managed-device process.

Only the sender may reach the phone's configured HTTP port. Do not forward port 9292 to the public internet. For a cloud web host, require an explicit authenticated private VPN/tunnel to the campus network and verify routes/firewall/availability. Hosting the application does not supply SMS hardware. The web HTTPS URL and private gateway URL are different endpoints.

Initial hardware sizing is a testable estimate, not a purchase prescription: measure the provisional 5,000-student profile on a recorded Linux host, starting around 4 vCPU/8 GB RAM/SSD if available. Adjust from evidence. Device/SIM throughput must be measured separately with authorized test numbers and operator-approved limits.

## 3. Live activation and restart safety

Effective live permission requires **all** of the following:

1. Deployment-level live permission, default false and stored outside the database backup.
2. Completed administrator-confirmed configuration fingerprint: institute/contact/timezone, real schedules, rule, authorized recipients, templates, gateway capability and limits.
3. An explicitly armed current dispatcher generation, with recent administrator MFA, audit record and earliest automatic attendance date.
4. Global and gateway pause clear, no unresolved gateway ownership, and healthy authoritative database.
5. Fresh per-attempt eligibility, authorization, time, identity and budget checks.

Generate a cryptographically fresh runtime generation at **each sender process start**, held in that process's memory and advertised to the app. An approval matches that exact live generation. Restoring a database approval cannot recreate the process's generation. The deployment permission alone never arms sending. Provide an authenticated UI showing current generation/status and the effect of approving it. A container or child-process restart disarms that sender; do not silently re-arm from a saved environment variable or restored row. Alerts must clearly disclose this availability trade-off.

Substantive gateway/rule/recipient-policy/template/schedule changes invalidate the relevant activation fingerprint and require renewed configuration review where safety changes. Routine attendance finalization does not. Switching simulator to live creates no queued live work from simulation. The operator selects an explicit effective date, and old simulation runs remain separate evidence.

Emergency pause is immediately available to permitted operators. It stops new attempts; already submitted requests cannot be recalled. Resume is an audited distinct action and does not bypass generation approval. Gateway quarantine after uncertainty also requires proof the old sender/request is no longer active, not just a timeout counter reset.

## 4. Backups, restoration, upgrade and rollback

Gemini must supply executable, documented backup/restore commands or scripts for the actual Compose service names it implements, plus a completed synthetic restore exercise. This planning package deliberately does not invent existing commands. Back up PostgreSQL data/schema, private file evidence needed by policy, configuration manifests and version information. Protect secrets/keys separately and test their recoverability. Broker contents are not the authoritative backup.

Restore procedure to implement and test:

1. Stop dispatch workers, disable external live permission and block gateway egress **before** opening a restored database to application traffic.
2. Restore into isolation; check backup integrity, schema/version compatibility, available keys and access controls.
3. Start fresh disarmed runtime generations; set global/gateway pause and LIVE off. Never carry over a prior approval token.
4. Preserve known accepted/unknown suppression. Mark restored in-flight attempts UNKNOWN and keep their budget allocations conservative.
5. Reconcile post-backup sending against independent restricted operational evidence if available. An old database cannot establish which messages were sent after the backup. If evidence is incomplete, suppress automatic sending for the entire uncertain interval, including the current day if necessary.
6. Set the minimum automatic date strictly after that uncertain interval. Clear stale broker work or let it become harmless no-ops; reconstruct due work from the database rather than replaying queue history.
7. Run simulator and data-integrity checks. Record achieved restore time and data-loss window. Reopen staff read/write access as appropriate.
8. Only an authorized operator can re-enable egress/deployment permission and arm the new generation after review. Historical work remains manual-review-only.

A raw in-place database overwrite while an armed sender continues running is unsupported and unsafe. Restrict restore credentials and document that such recovery must go through the shutdown/isolation procedure. If host and database fail together, the new sender generation is disarmed by construction. The plan does not promise recovery of lost physical-send history without independent evidence.

RPO/RTO, retention duration, backup frequency and off-site custody are institute decisions; propose and measure them during onboarding rather than declaring unmeasured recovery guarantees. Restore testing must include a backup taken before an accepted same-day SMS, then prove restoration cannot replay it automatically.

Upgrade flow: pause/disarm → verified backup → staging restore/migration rehearsal → dependency/security review → migration and static build → smoke/simulator checks → new generation review → resume. Prefer backward-compatible expand/contract migrations. Rollback application image only when schema compatibility is proven; never blindly run destructive reverse migrations. Schema/data rollback is a restore operation and inherits replay safeguards.

## 5. Operational signals and runbook

Health checks: `/health/live/` indicates process health; `/health/ready/` checks essential web/database dependencies without secrets. Report broker/worker/scheduler/gateway state separately because attendance entry may remain useful during an SMS outage. No readiness probe sends an SMS. Detailed status is authenticated.

Metrics: age of oldest eligible queue item and unpublished event; reconciliation/beat/worker heartbeats; missing registers by responsible scope; blocked reason counts; accepted/failed/unknown attempts; runtime disarmed/quarantined state; segments reserved/consumed/remaining; budget/window insufficiency; import errors; backup freshness and last restore exercise. Monitor without names/phones as metric labels. Configure thresholds from schedule and measured capacity; provide in-app operational alerts and daily summaries, not automatic health SMS.

| Incident | Operator response the UI/runbook must support |
|---|---|
| Phone offline / power or network loss | Check trusted reachability/power/address; classify pre-submit errors accurately; pause if uncertainty, resume only inside valid window |
| SIM allowance or permission rejected | Stop new calls, inspect device/SIM with operator, fix configuration; no repeated test messages or assumption stat=true means delivery |
| Invalid gateway credential | Show sanitized authentication failure; rotate secret through protected mechanism; no secret in logs/browser |
| Missing registers | Identify exact faculty/session/student scope; complete or legitimately cancel; never bulk-infer absences |
| Queue backlog / insufficient budget | Show drain-time/segment estimates; prioritize by configured deterministic order, review capacity; expire at close rather than spill into tomorrow |
| Unknown outcome | Preserve evidence/consumption, suppress auto retry, settle prior process; manual resend only with explicit duplicate-risk approval |
| Database outage / connection loss mid-send | Stop new dispatch, retain uncertain attempt; recover DB and quarantine sender where needed |
| Redis or scheduler outage | Keep academic writes/outbox durable; restore service and reconcile today's work; no historical catch-up |
| Accidental absence / post-send correction | Apply authorized reasoned correction; cancel unstarted work; explain no recall and optional separately approved correction message |
| Emergency pause / restart | Pause, display in-flight limits; new sender generation stays disarmed until reviewed |
| Incorrect import | Review staged errors before commit; for committed real data use a reasoned correction plan, not destructive mass deletion |

## 6. Test architecture

All automated SMS tests use the simulator and synthetic data. CI/test containers have no real gateway secrets or route. Mark fixtures clearly synthetic, including sample departments/identifiers and contacts. Use obviously labeled fake data, and never let a demo number become a real endpoint through mode switching.

Use pure unit tests for policies/templates/normalization/segment boundaries; PostgreSQL integration tests for constraints, temporal histories and transaction behavior; multiple real connections/processes for locks/concurrency; actual Redis/Celery and HTTP simulator processes for redelivery/outage/crashes; and browser tests for end-to-end authorization and UI behavior. SQLite or eager Celery cannot establish the production concurrency guarantees.

Use injected clock/timezone for date/DST cases. Use explicit fault hooks and process termination for crash windows. Assert simulator submission ledger counts independently from application rows. Test the actual configured timeout/retry/acknowledgment behavior. Avoid tests that only reproduce private implementation helpers without observing outcomes.

### Requirement-to-test matrix

IDs correspond to the original brief's section 12 acceptance criteria. Every row needs implementation file/test name, exact command, result and evidence path added by Gemini.

| ID | Required observable proof | Test layer |
|---|---|---|
| AC-01 | Complete all-ABSENT day → one intent and one simulator submission per designated unique number | Integration + end-to-end |
| AC-02 | PRESENT/LATE/EXCUSED/UNMARKED, unfinished/missing register, inactive enrollment, wrong date and zero held sessions prevent default notice | Policy table + DB |
| AC-03 | Missing/invalid/unauthorized contacts and disabled preferences produce distinct actionable blockers | Integration + browser |
| AC-04 | Holidays/weekends, instructional overrides, timezone, DST gap/fold, late finalization and exact close boundary | Clock-controlled integration |
| AC-05 | Repeated scans/tasks/clicks/imports and concurrent workers yield no duplicate automatic calls | Multi-process + independent simulator ledger |
| AC-06 | Correction before preparation stops work; after preparation UI accurately warns cancellation is uncertain | Concurrent transactions + browser |
| AC-07 | Phone/guardian/template/schedule edits after accepted/unknown do not create new automatic sends | Integration + concurrency |
| AC-08 | 200/false not accepted; strict true only accepted; no Delivered label; wrong JSON types blocked/unknown | Adapter contract + UI |
| AC-09 | Kill before/after preparation, during submission, after acceptance and before result commit; ambiguous outcomes never auto-retry | Process crash injection |
| AC-10 | Auth error, malformed body, offline gateway, DNS/connect/read failures, broker/DB outages and restarts recover safely | Fault-injected services |
| AC-11 | Every sensitive route/action/export/import/admin path enforces capability and object scope | Negative security matrix |
| AC-12 | Shared segment caps/pacing under races; Unicode/extensions/non-BMP; serialization; emergency pause and mode isolation | Unit + multi-worker |
| AC-13 | Restore old same-day backup and stale tasks; external arm/new generation prevents replay | Isolated restore exercise |
| AC-14 | Admin setup → students/guardians/enrollment/timetable/faculty → finalized attendance → summary → scheduled simulator dispatch → staff/audit view | Complete browser journey |
| AC-15 | Electives, lab groups, multi-period labs, cancelled/extra/replacement classes, revisions and substitutions preserve correct expectation sets | Domain fixtures + DB |
| AC-16 | Alternative rules wait for complete day, consolidate once and use correct partial-day/count-unit wording | Policy + template + end-to-end |
| AC-17 | HOD department isolation, faculty offering/section/group/session isolation, expired substitutes | Permission matrix |
| AC-18 | Hall-ticket strings/imports, lateral entry, section transfer, readmission and regulation history preserve prior attendance | Import + temporal model |
| AC-19 | Transparent policy-backed numerators/denominators; N/A at zero; counts without policy; no eligibility claims | Report integration + browser |
| AC-20 | Siblings share number without merging notices; duplicate links dedup within student; opt-out and international normalization work | Recipient integration |

Additional required tests: incomplete schedule materialization cannot appear complete; dirty scope blocks a stale summary before recalculation; roster correction races finalization; faculty loses rights between import preview and commit; global pause races dispatch; advisory-lock/DB loss cannot start an overlapping replacement; published outbox task loss is reconciled; manual test/resend shares budget; expired generation cannot send; contact snapshots differ correctly from current profile; export formula protection and audit log redaction; approved API response origin versus proxy errors.

### UI, accessibility and performance evidence

Inspect all six screen families and onboarding at 360×800, 768×1024 and 1440×900. Include empty/loading/error/conflict/offline/expired/unknown states. Keyboard-test login/MFA, import preview, register marking/finalization, filters, dialogs and notifications. Verify accessible names, focus restoration after HTMX swaps, error summaries, contrast, screen-reader save announcements, 200% zoom/reflow and reduced-motion behavior. Automated accessibility scanning supplements manual evidence; it is not WCAG certification.

Measure the architecture's provisional synthetic capacity profile, recording hardware/container limits, row counts, concurrency, p50/p95 latency, queries and backlog age. Separate web/queue performance from physical gateway capacity. Inspect query plans for roster/report bottlenecks and ensure no per-student query explosion. Do not load-test a real phone automatically.

### Checks and evidence record

Discover commands from the implemented repository. Record the actual environment and commands for formatting/linting, configured type checks, unit/integration/concurrency/security/browser tests, dependency/license/security audit, lockfile integrity, migration checks, static asset production build, container build and Django deployment checks. A new project must add repeatable scripts and CI entries for these checks. Do not claim commands exist in this planning-only workspace.

For each check record date, source revision, dependency lock fingerprint, environment, command, exit result, artifact/log path, and any failed/unavailable conditions. Screenshots use synthetic data. Mark acceptance cases PASS, FAIL or NOT RUN with evidence; never infer a pass from a written test. Re-run affected checks after fixes, then update TASKS.md.

## 7. Implementation phases and gates

| Phase | Deliverable | Gate before marking complete |
|---|---|---|
| P0 | Dependency/source recheck, Linux Compose, app skeleton, settings, migrations and repeatable checks | Fresh isolated startup, migration, health and simulator-only defaults |
| P1 | Custom user, MFA, scoped grants, audit, institute settings | No IDOR/MFA-admin bypass; protected actions audited |
| P2 | Academics/people/history, calendar/timetable, frozen rosters and staged CSV imports | Temporal/roster/atomic import constraints and missing-plan test pass |
| P3 | Usable attendance register, drafts, finalization/corrections, per-student daily projection | Real DB conflict/correction/elective/lab tests pass |
| P4 | OpenSMS adapter, HTTP simulator, immutable templates/segments/recipient intent | Contract/failure/identity tests pass without physical sends |
| P5 | Outbox, reconciliation, attempts, serialization/budgets, pause/live generations and restore safety | Multi-process crashes, redelivery, budget races and restore exercise pass |
| P6 | Remaining dashboards/reports/admin/wizard, responsive accessibility, operational runbooks | Full browser journey and UI/performance evidence; no fake metrics/buttons |
| P7 | Complete CI/evidence, docs, sample files, license notices and operator handoff | All AC rows pass or explicitly disclosed unresolved; no unsupported production claims |

Build a working vertical slice early (one synthetic student, one session, one simulated parent notice), then expand coverage. Security, object scope, history and reliability tests are introduced with their features; do not defer them to UI polish. Update progress as each gate is actually proven.

## 8. Controlled physical test, performed later by the institute

Keep automation in simulator mode. A permitted operator confirms a private managed device, owned/authorized test recipient, exact message preview, segment estimate, limits, current time and recent MFA. The operator explicitly requests one TEST notification through the same ledger and sender pipeline. Record API acceptance separately from any human-confirmed receipt/time on the test handset. Human observation is evidence for that test only, not a new gateway delivery capability.

Repeat only after reviewing the previous outcome; never auto-retry an unknown test. Verify short English, multipart, Telugu and international destinations only to the extent explicitly authorized and supported by the intended deployment. Record device/build/SIM/capability evidence and measured safe pacing. Test pause and restart/rearm behavior without student data. Actual sender activation and institutional/carrier approval remain operator responsibilities.

## 9. Final implementation deliverables

Source, migrations, exact dependency locks, CI/check commands, deterministic simulator/fault fixtures, synthetic seeds, sample student/attendance CSVs, Docker/Compose/env examples, connected screens, setup/user/operations guides, executed backup/restore scripts, architectural decisions and updated traceability. Handoff must say what works, how to start it using verified commands, what was tested and with what result, what remains unverified, and precisely which operator inputs block live use. No real student messages, public deployment or service purchase is authorized merely by this plan.
