"""
Seed the stock ledger from the legacy Product.stock_qty counter.

Each product with stock gets one opening batch plus one ADJUSTMENT movement, so that from
here on available stock is derived from the ledger instead of a mutable integer.

IMPORTANT: opening batches have NO best_before, because the shelf life of stock that
existed before batch tracking is unknown. Edit or write off those batches in the admin
before relying on expiry alerts. Flagged in docs/BUILD_LOG.md under Assumptions.

Reversible: the reverse operation removes only the rows this migration created.
"""

from django.db import migrations
from django.utils import timezone

OPENING_REASON = "Opening balance migrated from Product.stock_qty"


def seed_opening_stock(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    Batch = apps.get_model("inventory", "Batch")
    StockMovement = apps.get_model("inventory", "StockMovement")

    today = timezone.localdate()
    now = timezone.now()

    for variant in ProductVariant.objects.select_related("product").filter(is_default=True).iterator():
        quantity = int(variant.product.stock_qty or 0)
        if quantity <= 0:
            continue
        batch_code = f"OPENING-{variant.sku}"[:64]
        if Batch.objects.filter(batch_code=batch_code).exists():
            continue
        batch = Batch.objects.create(
            batch_code=batch_code,
            variant=variant,
            manufactured_on=today,
            best_before=None,
            quantity_produced=quantity,
            cost_per_unit_paise=0,
            production_notes=OPENING_REASON,
            created_at=now,
        )
        StockMovement.objects.create(
            variant=variant,
            batch=batch,
            kind="ADJUSTMENT",
            quantity=quantity,
            channel="MANUAL",
            reason=OPENING_REASON,
            reference_type="migration",
            reference_id="inventory.0002",
            actor_label="system:migration",
            created_at=now,
        )


def remove_opening_stock(apps, schema_editor):
    Batch = apps.get_model("inventory", "Batch")
    StockMovement = apps.get_model("inventory", "StockMovement")

    StockMovement.objects.filter(reference_type="migration", reference_id="inventory.0002").delete()
    Batch.objects.filter(production_notes=OPENING_REASON, movements__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
        ("catalog", "0002_backfill_default_variants"),
    ]

    operations = [
        migrations.RunPython(seed_opening_stock, remove_opening_stock),
    ]
