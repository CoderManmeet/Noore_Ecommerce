"""
Phase G1: integer paise twin beside every Decimal money column on CartOrder, plus the
coupon_code text snapshot.

Additive and reversible (reverse drops only the new columns).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0029_cart_paise_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartorder",
            name="sub_total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="shipping_amount_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="tax_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="service_fee_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="initial_total_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="saved_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cartorder",
            name="coupon_code",
            field=models.CharField(blank=True, default="", max_length=1000),
        ),
    ]
