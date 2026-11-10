"""
Notification generation and dispatch services.

Implements the notification pipeline and transactional outbox.
"""
import hashlib
import logging
from datetime import date, datetime, time, timezone
from typing import Optional

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.attendance.models import DailyAttendanceSummary, DailySummaryDecisionChoices
from apps.notifications.models import (
    AbsenceRuleChoices,
    DailyNotificationIntent,
    DeliveryAttempt,
    DeliveryAttemptOutcomeChoices,
    DeliveryAttemptPhaseChoices,
    DestinationDispatchGuard,
    DispatchControl,
    MessageTemplateVersion,
    Notification,
    NotificationKindChoices,
    NotificationPayloadVersion,
    NotificationPolicyVersion,
    NotificationStatusChoices,
    OutboxEvent,
    RecipientSlot,
)
from apps.people.models import Student, StudentGuardianLink
from apps.gateways.provider import DeterministicSimulator, OpenSmsAdapter, SendRequest, SendOutcome
from apps.gateways.models import GatewayBudgetDay, GatewayConfig
from apps.gateways.segment_estimator import estimate_segments

logger = logging.getLogger(__name__)


def generate_daily_notifications_for_date(target_date: date, namespace: str = "live") -> dict:
    """
    Evaluates all qualifying students for target_date and stages DailyNotificationIntent,
    RecipientSlots, and Notifications. Writes OutboxEvents for eligible ones.
    """
    summaries = DailyAttendanceSummary.objects.filter(
        summary_date=target_date,
        is_dirty=False,
        decision=DailySummaryDecisionChoices.ELIGIBLE_ABSENT,
    ).select_related("student")

    active_policy = NotificationPolicyVersion.objects.filter(
        is_active=True,
        effective_from__lte=target_date,
    ).filter(
        __import__("django.db.models", fromlist=["Q"]).Q(effective_until__isnull=True) |
        __import__("django.db.models", fromlist=["Q"]).Q(effective_until__gte=target_date)
    ).first()

    results = {
        "qualifying_students": summaries.count(),
        "intents_created": 0,
        "notifications_queued": 0,
        "notifications_blocked": 0,
    }

    for summary in summaries:
        student = summary.student

        with transaction.atomic():
            intent, created = DailyNotificationIntent.objects.get_or_create(
                namespace=namespace,
                student=student,
                attendance_date=target_date,
                kind=NotificationKindChoices.DAILY_ABSENCE,
                defaults={
                    "policy_version": active_policy,
                    "intent_status": NotificationStatusChoices.QUEUED,
                }
            )
            if created:
                results["intents_created"] += 1

            # Resolve eligible guardian links
            links = StudentGuardianLink.objects.filter(
                student=student,
                is_designated_recipient=True,
            ).select_related("guardian", "contact")

            eligible_links = [l for l in links if l.is_eligible_for_notification(as_of=target_date)]

            if not active_policy or not active_policy.notify_all_designated:
                if eligible_links:
                    eligible_links = [eligible_links[0]]

            if not eligible_links:
                intent.intent_status = NotificationStatusChoices.BLOCKED
                intent.block_reason = "No eligible designated guardian with active valid phone"
                intent.save(update_fields=["intent_status", "block_reason"])
                results["notifications_blocked"] += 1
                continue

            # Deduplicate by destination phone number
            seen_numbers = set()
            for link in eligible_links:
                raw_dest = str(link.contact.normalized_number)
                if raw_dest in seen_numbers:
                    continue
                seen_numbers.add(raw_dest)

                slot_key = f"{student.id}_{link.id}"
                slot, _ = RecipientSlot.objects.get_or_create(
                    intent=intent,
                    stable_slot_key=slot_key,
                    defaults={
                        "guardian_id_snapshot": link.guardian_id,
                        "link_id_snapshot": link.id,
                        "contact_id_snapshot": link.contact_id,
                        "frozen_destination": raw_dest,
                    }
                )

                # Create Notification
                notif, notif_created = Notification.objects.get_or_create(
                    intent=intent,
                    recipient_slot=slot,
                    defaults={
                        "status": NotificationStatusChoices.QUEUED,
                        "is_simulation": (namespace != "live"),
                    }
                )

                if notif_created:
                    results["notifications_queued"] += 1
                    # Render payload
                    rendered_msg = (
                        f"Dear Parent, {student.full_name} ({student.hall_ticket_number}) "
                        f"was marked absent for all held classes on {target_date}. "
                        "- Avanthi Institute"
                    )
                    est = estimate_segments(rendered_msg)
                    payload = NotificationPayloadVersion.objects.create(
                        notification=notif,
                        rendered_text=rendered_msg,
                        destination=raw_dest,
                        estimated_segments=est["segments"],
                    )

                    # Create OutboxEvent
                    OutboxEvent.objects.create(
                        event_type=OutboxEvent.EventTypeChoices.NOTIFICATION_QUEUED,
                        payload={"notification_id": str(notif.id)},
                        due_at=django_timezone.now(),
                    )

    return results


def dispatch_single_notification(notification_id: str, dry_run: bool = False) -> dict:
    """
    Acquires locks, runs all pre-flight guards, creates durable DeliveryAttempt BEFORE external HTTP,
    calls provider, and truthfully updates outcome. Never claims delivery.
    """
    from apps.institution.models import InstituteSettings

    with transaction.atomic():
        notif = Notification.objects.select_for_update().select_related(
            "intent", "recipient_slot", "intent__student"
        ).get(id=notification_id)

        if notif.status in (NotificationStatusChoices.DISPATCH_ACCEPTED, NotificationStatusChoices.UNKNOWN_OUTCOME):
            return {"status": "skipped", "reason": f"Already terminal state: {notif.status}"}

        inst = InstituteSettings.get_or_create_singleton()
        control = DispatchControl.objects.first()
        if control and control.is_globally_paused:
            return {"status": "blocked", "reason": "Dispatch globally paused"}

        payload = notif.payload_versions.order_by("-created_at").first()
        if not payload:
            return {"status": "error", "reason": "No payload version found"}

        dest = payload.destination
        student = notif.intent.student
        att_date = notif.intent.attendance_date

        # Destination guard
        guard, _ = DestinationDispatchGuard.objects.get_or_create(
            namespace=notif.intent.namespace,
            student=student,
            attendance_date=att_date,
            disclosure_family="absence",
            destination_key=dest,
            defaults={"locked_notification": notif}
        )

        if guard.has_possible_submission:
            return {"status": "blocked", "reason": "Prior possible submission exists for destination"}

        # Select gateway
        gw = GatewayConfig.objects.filter(is_active=True, is_paused=False).first()
        if not gw:
            gw = GatewayConfig.objects.create(
                name="Default Simulator",
                host="127.0.0.1",
                port=9292,
                is_simulator=True,
                is_active=True,
            )

        # Create DeliveryAttempt BEFORE external request
        attempt = DeliveryAttempt.objects.create(
            notification=notif,
            attempt_number=notif.delivery_attempts.count() + 1,
            dispatcher_generation=inst.dispatcher_generation,
            is_simulation=(notif.is_simulation or gw.is_simulator),
            gateway=gw,
            payload_version=payload,
            phase=DeliveryAttemptPhaseChoices.DURING_REQUEST,
            outcome=DeliveryAttemptOutcomeChoices.PENDING,
            attempt_started_at=django_timezone.now(),
        )

        notif.status = NotificationStatusChoices.DISPATCHING
        notif.save(update_fields=["status"])

    # Now make the external request outside the DB lock
    req = SendRequest(
        attempt_id=str(attempt.id),
        destination=dest,
        message_text=payload.rendered_text,
        estimated_segments=payload.estimated_segments,
        is_simulation=(notif.is_simulation or gw.is_simulator),
    )

    if gw.is_simulator:
        provider = DeterministicSimulator(gateway_id=str(gw.id))
    else:
        provider = OpenSmsAdapter(host=gw.host, port=gw.port, api_key_env_ref=gw.api_key_env_ref)

    result = provider.send(req)

    # Re-acquire lock to update outcome
    with transaction.atomic():
        attempt.refresh_from_db()
        attempt.http_status_code = result.http_status_code
        attempt.gateway_stat_value = result.gateway_stat_value
        attempt.error_message = result.error_message
        attempt.attempt_ended_at = django_timezone.now()
        attempt.phase = DeliveryAttemptPhaseChoices.AFTER_RESPONSE

        if result.outcome == SendOutcome.DISPATCH_ACCEPTED:
            attempt.outcome = DeliveryAttemptOutcomeChoices.DISPATCH_ACCEPTED
            notif.status = NotificationStatusChoices.DISPATCH_ACCEPTED
            guard.has_possible_submission = True
            guard.save(update_fields=["has_possible_submission"])
        elif result.outcome == SendOutcome.UNKNOWN_OUTCOME:
            attempt.outcome = DeliveryAttemptOutcomeChoices.UNKNOWN_OUTCOME
            notif.status = NotificationStatusChoices.UNKNOWN_OUTCOME
            guard.has_possible_submission = True
            guard.save(update_fields=["has_possible_submission"])
        else:
            attempt.outcome = DeliveryAttemptOutcomeChoices.FAILED_POST_SUBMIT
            notif.status = NotificationStatusChoices.FAILED
            notif.block_reason = result.error_message

        attempt.save()
        notif.save(update_fields=["status", "block_reason"])

    return {
        "status": "success",
        "attempt_id": str(attempt.id),
        "outcome": attempt.outcome,
        "notification_status": notif.status,
    }

