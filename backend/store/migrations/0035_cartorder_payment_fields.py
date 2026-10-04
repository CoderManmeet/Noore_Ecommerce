"""
Phase G3: payment provider, Razorpay ids, COD confirmation, owner-attention flag and
delivered-at timestamp on CartOrder.

Additive and reversible (reverse drops only the new columns).
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0034_couponredemption"),
    ]

    operations = [
        migrations.AddField(
            model_name='cartorder',
            name='cod_confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='cod_confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='delivered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='needs_attention',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='payment_provider',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='razorpay_order_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='cartorder',
            name='razorpay_payment_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
