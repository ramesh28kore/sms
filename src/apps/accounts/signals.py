"""Signal handlers for accounts app."""
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """Log successful logins to audit system."""
    try:
        from apps.audit.services import record_event
        record_event(
            actor=user,
            action="user.login",
            target_object=user,
            request=request,
        )
    except Exception:
        pass  # Never break login over audit failure


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request, **kwargs):
    """Log failed logins to audit system."""
    try:
        from apps.audit.services import record_event
        record_event(
            actor=None,
            action="user.login_failed",
            metadata={"username_attempted": credentials.get("username", "")[:64]},
            request=request,
        )
    except Exception:
        pass

