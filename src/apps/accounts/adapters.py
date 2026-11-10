"""
django-allauth adapter: disables public registration.
All user accounts must be created by administrators through the admin panel.
"""
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.http import HttpRequest


class NoSignupAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        """
        Disable self-service signup.
        Administrators create accounts via the management command or admin panel.
        """
        return False

