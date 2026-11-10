from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from apps.accounts.models import User, RoleChoices, ScopedRoleGrant


class Command(BaseCommand):
    help = "Bootstrap the initial Institute Administrator account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@avanthi.edu.in")
        parser.add_argument("--password", default=None)
        parser.add_argument("--name", default="Institute Administrator")

    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        password = options["password"] or get_random_string(16)
        full_name = options["name"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "full_name": full_name,
                "is_staff": True,
                "is_superuser": True,
            }
        )
        user.set_password(password)
        user.save()

        # Grant admin scoped role
        grant, _ = ScopedRoleGrant.objects.get_or_create(
            user=user,
            role=RoleChoices.ADMIN,
            defaults={
                "can_reveal_contacts": True,
                "can_export": True,
                "can_correct_attendance": True,
                "can_manage_gateway": True,
                "can_activate_live": True,
                "can_manual_resend": True,
            }
        )

        status_str = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{status_str} Administrator: {username} / {password}"
        ))

