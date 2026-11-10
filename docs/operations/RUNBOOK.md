# Avanthi Attendance & Parent Alerts — Operational Guide & Runbook

## Overview
- **Product Title**: Avanthi Attendance & Parent Alerts
- **Institute Name**: Avanthi Institute of Engineering and Technology
- **Academic Context**: B.Tech | JNTUH
- **Default Mode**: `SIMULATOR` (No real SMS is transmitted until explicitly activated by an administrator)

---

## 1. Quickstart & Local Operation

### Using Python Virtual Environment (Local Testing)
```powershell
# Activate environment
.\.venv\Scripts\Activate.ps1

# Run migrations
python src/manage.py migrate --settings=config.settings.testing

# Execute automated verification suite
pytest tests/test_attendance_and_notifications.py tests/test_acceptance_criteria.py --ds=config.settings.testing

# Start local web development server
python src/manage.py runserver 127.0.0.1:8000 --settings=config.settings.development
```

### Using Docker Compose (Production / Staging)
```bash
docker compose up -d --build
docker compose exec web python manage.py migrate --noinput
```

---

## 2. OpenSMS Upstream Contract & Hardware Setup
- **Target Repository**: [daslearning-org/OpenSMS](https://github.com/daslearning-org/OpenSMS)
- **Reviewed Commit**: `810c20de0e512bd0e92094d550a6ddef58a6e286`
- **Port**: Default `9292`
- **Endpoint**: `POST /sms/` with JSON `{"number": "+91...", "text": "..."}`
- **Authentication**: `Authorization: Bearer <API_KEY>`

### Critical Operational Limitations
1. `stat=true` represents **gateway dispatch accepted only**, **NOT handset delivery confirmed**.
2. Upstream OpenSMS Android implementation calls Android `SmsManager` without delivery callbacks.
3. Network timeouts or ambiguous connection losses after submission become **UNKNOWN_OUTCOME** to strictly prevent accidental duplicate physical dispatches.
4. **Android Power & Wi-Fi Management**: Android OS background restrictions, battery saver modes, and dynamic Wi-Fi IP reassignment can cause the OpenSMS server to become unreachable. Use a dedicated Android device with static IP assignment and background battery execution unrestricted.

---

## 3. Operational Runbook & Emergency Controls

| Incident | Action |
|---|---|
| **Accidental Absence Entry / Mass Error** | Navigate to `/admin-panel/` and toggle **Emergency Pause All Dispatch**. This immediately blocks all pending worker tasks. |
| **Phone / Gateway Offline** | Worker records `FAILED_PRE_SUBMIT`. Notifications remain queued for retry within the local sending window. |
| **Ambiguous Timeout / Worker Crash** | Attempt marked `UNKNOWN_OUTCOME`. Automatic retries are strictly suppressed. An administrator can manually review and trigger a manual resend from the notification detail view. |
| **Database Restore** | After restoring from a PostgreSQL backup, the system disarms live dispatch and increments the dispatcher generation to ensure earlier messages are never automatically replayed. |

