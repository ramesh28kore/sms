# Source review and dependency evidence

Reviewed on **8 November 2026** for the architecture-only handoff. Documentation/source inspection is not a hardware test or a tested dependency lock. Gemini must recheck the selected versions and installed device build during implementation.

## 1. Local evidence

The workspace `D:\1.AVNT\SMS` was empty before this planning package. No existing source, manifests, local README/CLAUDE.md/TASKS.md/AGENTS.md were found. The user supplied prompt-writing preferences in chat and an attached product brief; that brief is preserved as [ORIGINAL_PRODUCT_BRIEF.md](../reference/ORIGINAL_PRODUCT_BRIEF.md). The user's current instruction is to stop after architecture and let Gemini Argon implement.

## 2. Pinned OpenSMS review

Repository: [daslearning-org/OpenSMS](https://github.com/daslearning-org/OpenSMS). Resolved `main` through the GitHub connector, then read the listed files **at the resolved commit**, not merely a moving branch.

Reviewed commit: [`810c20de0e512bd0e92094d550a6ddef58a6e286`](https://github.com/daslearning-org/OpenSMS/commit/810c20de0e512bd0e92094d550a6ddef58a6e286), timestamp `2026-11-06T13:55:46Z`, message: update readme with cli req (merge).

| File | Observed facts and architectural implication |
|---|---|
| [README.md](https://github.com/daslearning-org/OpenSMS/blob/810c20de0e512bd0e92094d550a6ddef58a6e286/README.md) | Local-network gateway, Android/default SIM and desktop modem paths; example POST `/sms/` uses bearer auth, `number`/`text`, port 9292. Application owns rate limits. Hosting alone supplies no SMS hardware |
| [app/services/postApi.py](https://github.com/daslearning-org/OpenSMS/blob/810c20de0e512bd0e92094d550a6ddef58a6e286/app/services/postApi.py) | String request fields; authentication and phone validation precede `send_sms`; response contains `stat`. Code logs destination numbers. `/control/` is a placeholder, not a health/status contract |
| [app/services/smsApi.py](https://github.com/daslearning-org/OpenSMS/blob/810c20de0e512bd0e92094d550a6ddef58a6e286/app/services/smsApi.py) | Android partitions text, calls SmsManager and supplies no sent/delivery callbacks. True indicates the invocation path returned; it does not establish handset delivery. Phone checking is syntactic; application normalization/authorization remain necessary |
| [app/services/serialMgr.py](https://github.com/daslearning-org/OpenSMS/blob/810c20de0e512bd0e92094d550a6ddef58a6e286/app/services/serialMgr.py) | Desktop initializes text/GSM mode and evaluates modem responses after writing. A false result may follow submission. Telugu/Unicode portability and delivery evidence are not established by this implementation |
| [LICENSE](https://github.com/daslearning-org/OpenSMS/blob/810c20de0e512bd0e92094d550a6ddef58a6e286/LICENSE) | Apache-2.0. Preserve applicable notices when redistributing upstream material; prefer a separate adapter, not a maintained fork |

No idempotency/reconciliation API, delivery receipt, bulk endpoint or trustworthy non-sending health endpoint was established by the reviewed send path. This is a statement about the inspected revision, not a claim about every future release or external device build. Verify the actual installed APK/CLI version and repeat contract fixtures if it differs.

Source blob IDs for repeatability:

| File | Git blob SHA |
|---|---|
| README.md | `f21570294b12939676ca9d46d29a5d1a13ef7b99` |
| postApi.py | `36cb52a08dcc7a7a5c71ba3900100208df664d71` |
| smsApi.py | `3fa5ba9073dd2c2f6e1b0f7b0a326c988f1e7c14` |
| serialMgr.py | `4e22ed52bc55ef57dca8350aae228dd9041999dd` |
| LICENSE | `49825ac2fb016df9051007220e0b7297ce0ab4bb` |

Architecture inference: without provider idempotency and a way to reconcile an uncertain submission, automatic retry cannot guarantee avoidance of duplicate physical messages. Therefore potentially submitted work becomes UNKNOWN and requires explicit review. The plan also isolates upstream logs because app-side redaction cannot change phone-side logging.

## 3. Primary technical references

| Source | Checked design support |
|---|---|
| [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) and [supported versions](https://www.djangoproject.com/download/) | 5.2 LTS and Python 3.13 compatibility; resolve latest supported patch when building |
| [Django PostgreSQL backend](https://docs.djangoproject.com/en/5.2/ref/databases/) | PostgreSQL 14+ support and psycopg 3 path; proposed PostgreSQL 17 meets this floor |
| [PostgreSQL version policy](https://www.postgresql.org/support/versioning/) | Supported major/minor lifecycle; select a maintained patch, not an unversioned image |
| [PostgreSQL 17 explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html) | Row/session advisory locks and their lifecycle; design combines locking with durable attempt state |
| [Celery 5.7 release notes](https://docs.celeryq.dev/en/stable/history/whatsnew-5.7.html) | Python 3.10–3.14 support; 3.13 fits the chosen framework baseline |
| [Celery introduction](https://docs.celeryq.dev/en/stable/getting-started/introduction.html) | Native Windows support limitation; use Linux containers/WSL2 |
| [Celery task behavior](https://docs.celeryq.dev/en/stable/userguide/tasks.html) and [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html) | Acknowledgment/redelivery and single-scheduler guidance; neither supplies business exactly-once guarantees |
| [django-allauth requirements](https://docs.allauth.org/en/latest/installation/requirements.html) and [MFA](https://docs.allauth.org/en/latest/mfa/introduction.html) | Compatible authentication candidate; documented TOTP, recovery and WebAuthn capabilities. Select TOTP/recovery initially |
| [HTMX documentation/security](https://htmx.org/docs/#security) | Server-rendered enhancement and security configuration; plan restricts sensitive history and untrusted HTML |
| [Tailwind CLI installation](https://tailwindcss.com/docs/installation/tailwind-cli) | Compiled CSS workflow; no production CDN dependency needed |
| [Android SmsManager](https://developer.android.com/reference/android/telephony/SmsManager) | Platform sending/partitioning and callback concepts; upstream's use determines available evidence |
| [SMS segment reference](https://www.twilio.com/docs/glossary/what-sms-character-limit) | Common GSM-7/Unicode single/multipart capacities; used for estimator context, not as an OpenSMS/carrier guarantee or a proposed Twilio integration |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Accessibility target for keyboard, focus, contrast, reflow and operable controls |
| [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) | Production configuration/security checks to execute on the implemented app |

## 4. Deliberately unverified

Exact dependency lock compatibility, installed Android/modem binary behavior, physical SIM/carrier delivery, Telugu rendering/encoding on intended hardware, actual campus network/capacity, institutional affiliation/address/department facts, legal/carrier requirements, and any JNTUH attendance/eligibility policy. None is represented as proven by this architecture. Dependency and hardware rechecks are explicit implementation/operator gates.
