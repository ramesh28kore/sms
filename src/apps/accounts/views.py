"""Views for accounts: login, logout, locked page, health endpoints."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.generic import TemplateView


class LockedOutView(TemplateView):
    """Displayed after too many failed login attempts (django-axes)."""
    template_name = "accounts/locked_out.html"


def root_redirect_view(request):
    if request.user.is_authenticated:
        return redirect("reporting:dashboard")
    return redirect("account_login")


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html", {"user": request.user})

