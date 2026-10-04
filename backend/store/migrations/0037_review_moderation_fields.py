"""
Phase G4: verified-purchase link and moderation fields on Review.

Additive and reversible (reverse drops only the new columns).
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0036_cartorder_oid_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name='review',
            name='moderated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='review',
            name='moderated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='review',
            name='order_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviews', to='store.cartorderitem'),
        ),
        migrations.AddField(
            model_name='review',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending moderation'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], db_index=True, default='PENDING', max_length=10),
        ),
    ]
