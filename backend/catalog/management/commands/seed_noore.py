"""
Seed the placeholder Noore Candles catalogue for LOCAL DEVELOPMENT (ROADMAP decision A2).

    python manage.py seed_noore

Creates three scents, each in three sizes, with opening stock booked through the stock
ledger, plus one demo coupon. Everything here is placeholder data: names, descriptions and
prices are not the brand's final catalogue.

Idempotent: running it again changes nothing that already exists. Refuses to run unless
DEBUG is True, so it can never touch a production database.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from addon.models import ConfigSettings
from catalog.models import ProductVariant
from core.audit import acting_as
from core.money import from_paise
from inventory.models import Batch
from inventory.services import receive_production
from store.models import Coupon, Product
from vendor.models import Vendor

SCENTS = (
    ("vanilla-bean", "Vanilla Bean"),
    ("sandalwood", "Sandalwood"),
    ("lavender", "Lavender"),
)

# (size label, weight in grams, selling price in paise, MRP in paise)
SIZES = (
    ("100 g", 100, 49900, 59900),
    ("200 g", 200, 79900, 94900),
    ("300 g", 300, 119900, 139900),
)

OPENING_UNITS = 20
DEMO_COUPON_CODE = "WELCOME10"


class Command(BaseCommand):
    help = "Create the placeholder Noore Candles catalogue for local development (DEBUG only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_noore only runs when DEBUG is True. It is for local development data.")

        with transaction.atomic(), acting_as(None, label="system:seed_noore"):
            if ConfigSettings.objects.first() is None:
                ConfigSettings.objects.create()
                self.stdout.write("created ConfigSettings (Rs 79 shipping, free from Rs 999, tax 0)")

            # Products are attached to the owner's shop when one exists, so they show up in
            # the owner dashboard. No shop is created here.
            shop = Vendor.objects.order_by("id").first()

            created_products = created_variants = stocked = 0
            for slug_part, scent in SCENTS:
                product, was_created = self._product(slug_part, scent, shop)
                created_products += int(was_created)
                for label, grams, price_paise, mrp_paise in SIZES:
                    variant, variant_created = self._variant(product, slug_part, label, grams, price_paise, mrp_paise)
                    created_variants += int(variant_created)
                    stocked += int(self._opening_stock(variant))

            coupon_created = self._coupon(shop)

        self.stdout.write(self.style.SUCCESS(
            f"seed_noore: {created_products} product(s), {created_variants} variant(s) and "
            f"{stocked} opening batch(es) created; demo coupon {DEMO_COUPON_CODE} "
            f"{'created' if coupon_created else 'already present'}."
        ))

    def _product(self, slug_part, scent, shop):
        slug = f"noore-{slug_part}"
        product = Product.objects.filter(slug=slug).first()
        if product is not None:
            return product, False
        _label, _grams, price_paise, mrp_paise = SIZES[0]
        product = Product.objects.create(
            title=f"{scent} Scented Candle",
            slug=slug,
            description=f"[PLACEHOLDER COPY] Hand-poured {scent.lower()} scented candle. Replace this text.",
            price=from_paise(price_paise),
            old_price=from_paise(mrp_paise),
            stock_qty=0,
            status="published",
            featured=True,
            vendor=shop,
        )
        return product, True

    def _variant(self, product, slug_part, label, grams, price_paise, mrp_paise):
        sku = f"NOORE-{slug_part.upper()}-{grams}G"
        variant = ProductVariant.objects.filter(sku=sku).first()
        if variant is not None:
            return variant, False

        fields = dict(
            sku=sku, name=label, options={"Size": label}, weight_grams=grams,
            price_paise=price_paise, mrp_paise=mrp_paise, perishable=False, active=True,
        )
        # Creating the product created its default variant; the smallest size takes that slot.
        default = ProductVariant.objects.filter(product=product, is_default=True).first()
        if default is not None and default.name == "Default" and not default.options:
            for name, value in fields.items():
                setattr(default, name, value)
            default.save()
            return default, True
        return ProductVariant.objects.create(product=product, is_default=False, **fields), True

    def _opening_stock(self, variant):
        batch_code = f"SEED-{variant.sku}"[:64]
        if Batch.objects.filter(batch_code=batch_code).exists():
            return False
        batch = Batch.objects.create(
            batch_code=batch_code, variant=variant, manufactured_on=timezone.localdate(), best_before=None,
            quantity_produced=OPENING_UNITS, cost_per_unit_paise=0,
            production_notes="Placeholder opening stock from seed_noore (local development)",
        )
        receive_production(variant, batch, OPENING_UNITS, reason="seed_noore opening stock")
        return True

    def _coupon(self, shop):
        if Coupon.objects.filter(code__iexact=DEMO_COUPON_CODE).exists():
            return False
        Coupon.objects.create(
            vendor=shop, code=DEMO_COUPON_CODE, kind="PERCENT", discount=10, active=True,
            max_uses_per_customer=1, max_total_uses=None,
        )
        return True
