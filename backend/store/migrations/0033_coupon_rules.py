"""
Phase G1: coupon rules. `kind` defaults to PERCENT so every existing coupon keeps its
meaning (the existing `discount` integer stays the percentage).

Additive and reversible (reverse drops only the new columns).
"""

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0032_backfill_paise_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="kind",
            field=models.CharField(choices=[("PERCENT", "Percentage off"), ("FLAT", "Flat rupees off")], default="PERCENT", max_length=10),
        ),
        migrations.AddField(
            model_name="coupon",
            name="flat_off_paise",
            field=models.BigIntegerField(default=0, help_text="FLAT coupons only: amount off, in paise (Rs 100 = 10000).", validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="coupon",
            name="min_order_paise",
            field=models.BigIntegerField(default=0, help_text="Minimum item subtotal, in paise, before this coupon applies. 0 = no minimum.", validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="coupon",
            name="max_total_uses",
            field=models.PositiveIntegerField(blank=True, help_text="Total number of orders that may use this coupon. Empty = unlimited.", null=True),
        ),
        migrations.AddField(
            model_name="coupon",
            name="max_uses_per_customer",
            field=models.PositiveIntegerField(default=1, help_text="How many orders one customer may use this coupon on."),
        ),
        migrations.AddField(
            model_name="coupon",
            name="valid_from",
            field=models.DateTimeField(blank=True, help_text="Empty = valid immediately.", null=True),
        ),
        migrations.AddField(
            model_name="coupon",
            name="valid_until",
            field=models.DateTimeField(blank=True, help_text="Empty = never expires.", null=True),
        ),
    ]
