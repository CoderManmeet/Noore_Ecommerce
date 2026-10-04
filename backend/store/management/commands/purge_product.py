"""
Erase a product completely, including its stock ledger rows. FOR TEST AND DEMO DATA ONLY.

The dashboard deliberately refuses to delete a product that has stock history, because the
stock ledger is permanent business history. That protection is right for a real product. It is
not what you want for the demo products the original course project shipped with, which is
what this command is for.

    python manage.py purge_product --list
    python manage.py purge_product --sku SKU36393
    python manage.py purge_product --slug hoodie-t-shirt-for-men --force
    python manage.py purge_product --demo --force        # every product from the course demo data

It shows exactly what will go and asks for confirmation unless --force is given. It REFUSES,
always, to erase a product that appears on any order: order history must stay intact, so such a
product has to be hidden instead. Back up first:

    Copy-Item backend\\db.sqlite3 "backups\\db-$(Get-Date -Format 'yyyyMMdd-HHmmss').sqlite3"
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from catalog.models import PriceHistory, ProductVariant
from core.audit import acting_as, record
from inventory.models import Batch, StockMovement, StockReservation
from store.models import CartOrderItem, Product

# The products the Udemy course project ships with. Matched by slug.
DEMO_SLUGS = (
    "hoodie-t-shirt-for-men",
    "converse-black-summer",
    "neon-rbg-room-colors",
    "sitting-room-side-stolls",
)


class Command(BaseCommand):
    help = "Erase a test or demo product completely, including its stock ledger rows."

    def add_arguments(self, parser):
        parser.add_argument("--sku", help="Product SKU, as shown in the dashboard list (with or without the leading #).")
        parser.add_argument("--slug", help="Product slug, as it appears in its web address.")
        parser.add_argument("--pid", help="Product pid.")
        parser.add_argument("--demo", action="store_true", help="Every product from the original course demo data.")
        parser.add_argument("--list", action="store_true", help="List products and exit, changing nothing.")
        parser.add_argument("--force", action="store_true", help="Do not ask for confirmation.")

    def handle(self, *args, **options):
        if options["list"]:
            self._list()
            return

        products = self._targets(options)
        if not products:
            raise CommandError("No product matched. Use --list to see what is there.")

        blocked = [p for p in products if CartOrderItem.objects.filter(product=p).exists()]
        if blocked:
            names = ", ".join(f'"{p.title}"' for p in blocked)
            raise CommandError(
                f"{names} appears on an order, so it cannot be erased: order history has to stay "
                "intact. Hide it from the shop instead (the eye button on the dashboard list)."
            )

        plan = [(product, self._counts(product)) for product in products]
        self.stdout.write("This will permanently erase:")
        for product, counts in plan:
            self.stdout.write(
                f'  "{product.title}" ({product.sku}) - {counts["variants"]} size(s), '
                f'{counts["movements"]} stock movement(s), {counts["batches"]} batch(es), '
                f'{counts["reservations"]} reservation(s), {counts["price_history"]} price-history row(s), '
                f'{counts["reviews"]} review(s), {counts["wishlist"]} wishlist entr(ies)'
            )

        if not options["force"]:
            answer = input("Type the word ERASE to continue: ").strip()
            if answer != "ERASE":
                self.stdout.write(self.style.WARNING("Nothing was changed."))
                return

        with transaction.atomic(), acting_as(None, label="system:purge_product"):
            for product, counts in plan:
                record(
                    "product.purged", product,
                    before={"title": product.title, "sku": product.sku, "slug": product.slug, **counts},
                    after=None, reason="test or demo product erased with purge_product",
                )
                self._erase(product)

        self.stdout.write(self.style.SUCCESS(f"Erased {len(plan)} product(s). The audit log records what went."))

    # ------------------------------------------------------------------ helpers

    def _list(self):
        self.stdout.write(f"{'SKU':<12} {'ORDERS':>6}  {'STATUS':<10} {'SLUG':<34} TITLE")
        for product in Product.objects.all().order_by("id"):
            orders = CartOrderItem.objects.filter(product=product).count()
            flag = "  (on an order: hide, do not erase)" if orders else ""
            self.stdout.write(
                f"{product.sku or '-':<12} {orders:>6}  {product.status or '-':<10} "
                f"{(product.slug or '-')[:34]:<34} {product.title}{flag}"
            )

    def _targets(self, options):
        if options["demo"]:
            return list(Product.objects.filter(slug__in=DEMO_SLUGS))
        for field, value in (("sku", options["sku"]), ("slug", options["slug"]), ("pid", options["pid"])):
            if value:
                return list(Product.objects.filter(**{field: str(value).lstrip("#").strip()}))
        raise CommandError("Give one of --sku, --slug, --pid or --demo (or use --list).")

    @staticmethod
    def _counts(product):
        variant_ids = list(product.variants.values_list("id", flat=True))
        return {
            "variants": len(variant_ids),
            "movements": StockMovement.objects.filter(variant_id__in=variant_ids).count(),
            "batches": Batch.objects.filter(variant_id__in=variant_ids).count(),
            "reservations": StockReservation.objects.filter(variant_id__in=variant_ids).count(),
            "price_history": PriceHistory.objects.filter(variant_id__in=variant_ids).count(),
            "reviews": product.reviews.count(),
            "wishlist": product.wishlist.count(),
        }

    @staticmethod
    def _erase(product):
        """
        Remove the ledger rows, then the product. The ledger tables are append-only in
        application code (that is the point of them), so this command - and only this command -
        removes those rows with direct SQL, inside the same transaction as everything else.
        """
        variant_ids = list(product.variants.values_list("id", flat=True))
        if variant_ids:
            placeholders = ", ".join(["%s"] * len(variant_ids))
            with connection.cursor() as cursor:
                for table in ("inventory_stockmovement", "inventory_stockreservation",
                              "inventory_batch", "catalog_pricehistory"):
                    cursor.execute(f"DELETE FROM {table} WHERE variant_id IN ({placeholders})", variant_ids)
        ProductVariant.objects.filter(product=product).delete()
        product.delete()