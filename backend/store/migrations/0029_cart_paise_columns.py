"""
Phase G1: integer paise twin beside every Decimal money column on Cart.

Additive and reversible (reverse drops only the new columns; the Decimal columns are untouched).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0028_variant_channel_cod_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="cart",
            name="price_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cart",
            name="sub_total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cart",
            name="shipping_amount_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cart",
            name="service_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cart",
            name="tax_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cart",
            name="total_paise",
            field=models.BigIntegerField(default=0),
        ),
    ]
