from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.notifications.models import (
    DailyNotificationIntent, Notification, NotificationStatusChoices,
    DeliveryAttempt, DeliveryAttemptOutcomeChoices
)
from apps.notifications.services import dispatch_single_notification, generate_daily_notifications_for_date
from apps.accounts.permissions import is_admin


@login_required
def notification_list_view(request):
    notifications = Notification.objects.all().select_related(
        "intent", "recipient_slot", "intent__student"
    ).order_by("-created_at")[:100]

    return render(request, "notifications/list.html", {
        "notifications": notifications,
        "is_admin": is_admin(request.user),
    })


@login_required
def trigger_daily_pipeline_view(request):
    if not is_admin(request.user):
        return redirect("reporting:dashboard")

    if request.method == "POST":
        today = timezone.localdate()
        from apps.institution.models import InstituteSettings
        inst = InstituteSettings.get_or_create_singleton()
        namespace = "live" if inst.sms_mode == "live" else "simulator"

        gen_res = generate_daily_notifications_for_date(today, namespace=namespace)

        dispatched_count = 0
        for n in Notification.objects.filter(status=NotificationStatusChoices.QUEUED, intent__attendance_date=today):
            dispatch_single_notification(str(n.id))
            dispatched_count += 1

        from django.contrib import messages
        messages.success(
            request,
            f"Daily Alert Pipeline executed for {today}: {gen_res.get('qualifying_students', 0)} absent students evaluated, "
            f"{gen_res.get('notifications_queued', 0)} notices generated, {dispatched_count} dispatched via {namespace.upper()}."
        )

    return redirect(request.META.get("HTTP_REFERER", "reporting:dashboard"))


@login_required
def notification_detail_view(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id)
    attempts = notif.delivery_attempts.all().order_by("-attempt_number")
    payload = notif.payload_versions.order_by("-created_at").first()

    return render(request, "notifications/detail.html", {
        "notification": notif,
        "attempts": attempts,
        "payload": payload,
        "can_resend": is_admin(request.user),
    })


@login_required
def manual_resend_view(request, notification_id):
    if not is_admin(request.user):
        return redirect("notifications:detail", notification_id=notification_id)

    if request.method == "POST":
        res = dispatch_single_notification(str(notification_id))
        return redirect("notifications:detail", notification_id=notification_id)

    return redirect("notifications:detail", notification_id=notification_id)

