"""
Phase G4: one review per user per product.

The first operation checks for existing duplicates and stops with a clear message if any
exist. Reverse removes the constraint.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields


def refuse_duplicates(apps, schema_editor):
    from django.db.models import Count

    Review = apps.get_model("store", "Review")
    duplicates = list(
        Review.objects.filter(user__isnull=False, product__isnull=False)
        .values("user_id", "product_id").annotate(n=Count("id")).filter(n__gt=1)[:20]
    )
    if duplicates:
        raise RuntimeError(
            "Cannot add the one-review-per-customer rule: some customers have more than one review "
            f"for the same product: {duplicates}. Delete the extra reviews in Django admin and run migrate again."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0038_approve_existing_reviews"),
    ]

    operations = [
        migrations.RunPython(refuse_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(condition=models.Q(('product__isnull', False), ('user__isnull', False)), fields=('user', 'product'), name='store_review_one_per_user_per_product'),
        ),
    ]
