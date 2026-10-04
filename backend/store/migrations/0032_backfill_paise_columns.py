"""
Phase G1: backfill every `<name>_paise` column from its Decimal twin.

Conversion is exact Decimal arithmetic (rupees x 100, rounded half-up to a whole paisa);
NULL Decimals become 0. No float is involved.

Reverse is a no-op: the Decimal columns were never changed, and rolling back the schema
migrations before this one drops the paise columns.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations

MONEY_FIELDS = {
    "Cart": ("price", "sub_total", "shipping_amount", "service_fee", "tax_fee", "total"),
    "CartOrder": ("sub_total", "shipping_amount", "tax_fee", "service_fee", "total", "initial_total", "saved"),
    "CartOrderItem": ("price", "sub_total", "shipping_amount", "tax_fee", "service_fee", "total", "initial_total", "saved"),
}


def _paise(value):
    if value is None:
        return 0
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def backfill(apps, schema_editor):
    for model_name, names in MONEY_FIELDS.items():
        model = apps.get_model("store", model_name)
        paise_names = [f"{name}_paise" for name in names]
        batch = []
        for row in model.objects.all().only("pk", *names).iterator(chunk_size=500):
            for name in names:
                setattr(row, f"{name}_paise", _paise(getattr(row, name)))
            batch.append(row)
            if len(batch) >= 500:
                model.objects.bulk_update(batch, paise_names)
                batch = []
        if batch:
            model.objects.bulk_update(batch, paise_names)


def noop(apps, schema_editor):
    """Nothing to undo: the Decimal columns are the untouched originals."""


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0031_cartorderitem_paise_columns"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
