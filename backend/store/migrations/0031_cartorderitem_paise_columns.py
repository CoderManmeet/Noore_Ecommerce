"""
Phase G1: integer paise twin beside every Decimal money column on CartOrderItem.

Additive and reversible (reverse drops only the new columns).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0030_cartorder_paise_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartorderitem",
            name="price_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="sub_total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="shipping_amount_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="tax_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="service_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="initial_total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="saved_paise",
            field=models.BigIntegerField(default=0),
        ),
    ]
