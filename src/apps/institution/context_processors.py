"""Context processor: inject institute settings into all templates."""
from functools import lru_cache

from django.conf import settings


def institute_context(request):
    """
    Provides institute_settings to all templates.
    Cached per process restart; settings changes take effect immediately via model.
    """
    try:
        from apps.institution.models import InstituteSettings
        inst = InstituteSettings.get_or_create_singleton()
        return {
            "institute_name": inst.institute_name,
            "institute_short_name": inst.approved_short_name,
            "academic_context": inst.academic_context_label,
            "sms_mode": inst.sms_mode,
            "is_live_mode": inst.sms_mode == "live",
            "institute_timezone": inst.timezone,
        }
    except Exception:
        # DB not yet set up (e.g. during migrations)
        return {
            "institute_name": "Avanthi Institute of Engineering and Technology",
            "institute_short_name": "Avanthi Institute",
            "academic_context": "B.Tech | JNTUH",
            "sms_mode": "simulator",
            "is_live_mode": False,
            "institute_timezone": "Asia/Kolkata",
        }

