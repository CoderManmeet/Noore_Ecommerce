"""
Phase G1: shipping and tax configuration, in integer paise / basis points.

Additive and reversible (reverse drops only the new columns).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("addon", "0002_rename_settings_configsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="configsettings",
            name="shipping_flat_paise",
            field=models.BigIntegerField(default=7900, help_text="Flat shipping charged once per order, in paise (Rs 79 = 7900)."),
        ),
        migrations.AddField(
            model_name="configsettings",
            name="free_shipping_threshold_paise",
            field=models.BigIntegerField(default=99900, help_text="Shipping is free when the subtotal after discount is at least this many paise (Rs 999 = 99900)."),
        ),
        migrations.AddField(
            model_name="configsettings",
            name="tax_rate_bps",
            field=models.PositiveIntegerField(default=0, help_text="Tax rate in basis points (18% = 1800). Prices are tax-inclusive: tax is carved out of the price, never added on top. 0 while the business is not GST-registered."),
        ),
    ]
