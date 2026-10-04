"""
Accounts for the Playwright smoke suite. NOT for real use.

    python manage.py seed_e2e

Creates an owner (staff) with a shop, and a customer, with fixed throwaway passwords. It
refuses to run unless DEBUG is True AND the database file is the smoke suite's own
(e2e.sqlite3), so it can never add known-password accounts to a real database.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

OWNER_EMAIL = "owner@e2e.test"
CUSTOMER_EMAIL = "customer@e2e.test"
PASSWORD = "E2e-only-Passw0rd!"


class Command(BaseCommand):
    help = "Create the owner and customer accounts used by the Playwright smoke suite (e2e database only)."

    def handle(self, *args, **options):
        database_name = str(settings.DATABASES["default"].get("NAME", ""))
        if not settings.DEBUG or not database_name.replace("\\", "/").endswith("/e2e.sqlite3"):
            raise CommandError("seed_e2e only runs with DEBUG=True against the smoke suite database (e2e.sqlite3).")

        from userauths.models import User
        from vendor.models import Vendor

        owner = User.objects.filter(email=OWNER_EMAIL).first()
        if owner is None:
            owner = User(email=OWNER_EMAIL, username="owner", full_name="E2E Owner", phone="9876500001", is_staff=True)
            owner.set_password(PASSWORD)
            owner.save()
        Vendor.objects.get_or_create(user=owner, defaults={"name": "Noore Candles", "email": OWNER_EMAIL, "slug": "noore-candles"})

        if not User.objects.filter(email=CUSTOMER_EMAIL).exists():
            customer = User(email=CUSTOMER_EMAIL, username="customer", full_name="E2E Customer", phone="9876500002")
            customer.set_password(PASSWORD)
            customer.save()

        self.stdout.write(self.style.SUCCESS("seed_e2e: owner and customer accounts are ready."))
