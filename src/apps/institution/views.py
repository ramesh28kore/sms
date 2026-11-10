from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.institution.models import InstituteSettings, Department
from apps.notifications.models import NotificationPolicyVersion, DispatchControl
from apps.gateways.models import GatewayConfig
from apps.accounts.permissions import is_admin


@login_required
def admin_panel_view(request):
    if not is_admin(request.user):
        return redirect("reporting:dashboard")

    inst = InstituteSettings.get_or_create_singleton()
    gateways = GatewayConfig.objects.all()
    policies = NotificationPolicyVersion.objects.all()
    departments = Department.objects.all()
    control = DispatchControl.objects.first()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_pause":
            if not control:
                control = DispatchControl.objects.create(is_globally_paused=True, paused_by=request.user)
            else:
                control.is_globally_paused = not control.is_globally_paused
                control.paused_by = request.user
                control.paused_at = timezone.now()
                control.save()
            return redirect("institution:admin_panel")

        elif action == "toggle_sms_mode":
            if inst.sms_mode == InstituteSettings.ModeChoices.SIMULATOR:
                inst.sms_mode = InstituteSettings.ModeChoices.LIVE
                inst.live_activated_at = timezone.now()
                inst.live_activated_by = request.user
            else:
                inst.sms_mode = InstituteSettings.ModeChoices.SIMULATOR
            inst.save()
            return redirect("institution:admin_panel")

        elif action == "update_gateway":
            gw_id = request.POST.get("gateway_id")
            host = request.POST.get("host", "").strip()
            port = int(request.POST.get("port", 9292))
            is_sim = request.POST.get("is_simulator") == "true"
            if gw_id:
                gw = GatewayConfig.objects.filter(id=gw_id).first()
                if gw:
                    gw.host = host
                    gw.port = port
                    gw.is_simulator = is_sim
                    gw.save()
            else:
                GatewayConfig.objects.create(
                    name="Primary OpenSMS Device",
                    host=host,
                    port=port,
                    is_simulator=is_sim,
                )
            return redirect("institution:admin_panel")

        elif action == "update_settings":
            inst.approved_short_name = request.POST.get("short_name", inst.approved_short_name)
            inst.official_contact = request.POST.get("contact", inst.official_contact)
            inst.save()
            return redirect("institution:admin_panel")

    return render(request, "admin_ui/panel.html", {
        "inst": inst,
        "gateways": gateways,
        "policies": policies,
        "departments": departments,
        "is_paused": control.is_globally_paused if control else False,
    })

