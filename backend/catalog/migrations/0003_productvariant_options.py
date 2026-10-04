"""
Phase G2: ProductVariant.options, the generic {option name: value} map the storefront's
variant picker is built from.

Additive and reversible (reverse drops only the new column).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_backfill_default_variants"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="options",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
