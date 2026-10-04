"""
Phase G3 (bug D12): CartOrder.oid becomes unique.

The first operation checks for duplicates and stops with a clear message if any exist, so
the constraint is never applied over bad data. Reverse removes the constraint.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields


def refuse_duplicates(apps, schema_editor):
    from django.db.models import Count

    CartOrder = apps.get_model("store", "CartOrder")
    duplicates = list(
        CartOrder.objects.values("oid").annotate(n=Count("id")).filter(n__gt=1).values_list("oid", flat=True)[:20]
    )
    if duplicates:
        raise RuntimeError(
            "Cannot make CartOrder.oid unique: these order ids are used by more than one order: "
            + ", ".join(duplicates)
            + ". Give the duplicates new ids (or remove them) and run migrate again."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0035_cartorder_payment_fields"),
    ]

    operations = [
        migrations.RunPython(refuse_duplicates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cartorder',
            name='oid',
            field=shortuuid.django_fields.ShortUUIDField(alphabet='abcdefghijklmnopqrstuvxyz', length=10, max_length=25, prefix='', unique=True),
        ),
    ]
