"""
Phase G2: one opening PriceHistory row per existing variant, so the history is complete
from the day it starts being recorded.

`effective_from` is the moment this migration runs: that is when recording began, and the
price a variant had before then is not known to this table.

Reverse deletes only the rows this migration wrote (actor_label "system:migration").
"""

from django.db import migrations
from django.utils import timezone

MIGRATION_LABEL = "system:migration"


def write_opening_rows(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    PriceHistory = apps.get_model("catalog", "PriceHistory")

    now = timezone.now()
    already = set(PriceHistory.objects.values_list("variant_id", flat=True))
    rows = [
        PriceHistory(
            variant_id=variant.pk,
            price_paise=variant.price_paise,
            mrp_paise=variant.mrp_paise,
            effective_from=now,
            actor=None,
            actor_label=MIGRATION_LABEL,
        )
        for variant in ProductVariant.objects.all().iterator()
        if variant.pk not in already
    ]
    PriceHistory.objects.bulk_create(rows, batch_size=500)


def delete_opening_rows(apps, schema_editor):
    PriceHistory = apps.get_model("catalog", "PriceHistory")
    PriceHistory.objects.filter(actor_label=MIGRATION_LABEL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_pricehistory"),
    ]

    operations = [
        migrations.RunPython(write_opening_rows, delete_opening_rows),
    ]
