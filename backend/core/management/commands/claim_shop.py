"""
Attach the brand's shop to a staff account.

This is a single-brand store, so there is exactly one shop and the owner's account should
own it. Use this after creating your own superuser to take over the shop (and therefore the
products, orders, coupons and reviews) that the seed data left attached to another account.

    python manage.py claim_shop --email you@example.com
    python manage.py claim_shop --email you@example.com --name "My Brand"
    python manage.py claim_shop --list
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.audit import acting_as, record
from store.models import Product
from userauths.models import User
from vendor.models import Vendor


class Command(BaseCommand):
    help = "Attach the brand's shop (and its products) to a staff account."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Email of the staff user who should own the shop.")
        parser.add_argument("--shop-id", type=int, help="Which shop to claim (default: the one with the most products).")
        parser.add_argument("--name", help="Rename the shop at the same time.")
        parser.add_argument(
            "--move-products",
            action="store_true",
            help="Also move products from every other shop onto the claimed one.",
        )
        parser.add_argument("--list", action="store_true", help="List shops and exit, changing nothing.")

    def handle(self, *args, **options):
        if "core_auditlog" not in connection.introspection.table_names():
            raise CommandError(
                "The core tables are missing. Run this first:\n    python manage.py migrate"
            )

        if options["list"]:
            self._list_shops()
            return

        email = options["email"]
        if not email:
            raise CommandError("--email is required (or use --list to see the shops).")

        try:
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist:
            raise CommandError(
                f"No account with email {email}. Create one with: python manage.py createsuperuser"
            )

        if not user.is_staff:
            raise CommandError(
                f"{user.email} is not a staff account, so it cannot own the shop.\n"
                "Make it staff in Django admin (Users > tick 'Staff status'), or create a "
                "superuser with: python manage.py createsuperuser"
            )

        shop = self._resolve_shop(options["shop_id"])

        with transaction.atomic(), acting_as(user, label=f"user:{user.pk}"):
            previous_owner = shop.user
            previous_name = shop.name

            if previous_owner is not None and previous_owner.pk != user.pk:
                self.stdout.write(f"Detaching shop from previous owner: {previous_owner.email}")

            # Vendor.user is one-to-one: release any other shop this user already holds.
            Vendor.objects.filter(user=user).exclude(pk=shop.pk).update(user=None)

            shop.user = user
            if options["name"]:
                shop.name = options["name"]
                shop.slug = ""  # regenerated from the new name by Vendor.save()
            if not shop.email:
                shop.email = user.email
            shop.active = True
            shop.verified = True
            shop.save()

            moved = 0
            if options["move_products"]:
                moved = Product.objects.exclude(vendor=shop).update(vendor=shop)

            record(
                "shop.claimed",
                shop,
                before={"user": previous_owner.pk if previous_owner else None, "name": previous_name},
                after={"user": user.pk, "name": shop.name},
                reason="claim_shop management command",
            )

        product_count = Product.objects.filter(vendor=shop).count()
        self.stdout.write(self.style.SUCCESS(f"\nShop '{shop.name}' (id {shop.pk}) now belongs to {user.email}"))
        self.stdout.write(f"  products in this shop: {product_count}")
        if options["move_products"]:
            self.stdout.write(f"  products moved from other shops: {moved}")
        self.stdout.write(
            self.style.WARNING(
                "\nLog out and log back in on the storefront. "
                "Your dashboard link is carried inside the login token, so it only updates on a fresh login."
            )
        )

    def _resolve_shop(self, shop_id):
        if shop_id is not None:
            try:
                return Vendor.objects.get(pk=shop_id)
            except Vendor.DoesNotExist:
                raise CommandError(f"No shop with id {shop_id}. Run with --list to see the shops.")

        shops = list(Vendor.objects.all())
        if not shops:
            raise CommandError(
                "There are no shops yet. Register one at /vendor/register/ on the storefront first."
            )
        shops.sort(key=lambda s: Product.objects.filter(vendor=s).count(), reverse=True)
        return shops[0]

    def _list_shops(self):
        shops = Vendor.objects.all().order_by("id")
        if not shops:
            self.stdout.write("No shops exist yet.")
            return
        self.stdout.write(f"{'id':>4}  {'products':>8}  {'owner':<32} name")
        self.stdout.write("-" * 78)
        for shop in shops:
            owner = shop.user.email if shop.user else "(nobody)"
            count = Product.objects.filter(vendor=shop).count()
            self.stdout.write(f"{shop.pk:>4}  {count:>8}  {owner:<32} {shop.name}")
