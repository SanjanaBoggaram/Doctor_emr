"""
Create (or reset) a default doctor account.

    python manage.py seed_doctor --username doctor --password clinic123

The doctor can also log into /admin (is_staff=True) to manage records.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update a doctor account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="doctor")
        parser.add_argument("--password", default="clinic123")
        parser.add_argument("--name", default="Clinic Doctor")

    def handle(self, *args, **opts):
        username = opts["username"]
        user, created = User.objects.get_or_create(username=username)
        user.role = User.Role.DOCTOR
        user.is_staff = True
        user.first_name = opts["name"]
        user.set_password(opts["password"])
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} doctor '{username}' (password: {opts['password']}).")
        )
