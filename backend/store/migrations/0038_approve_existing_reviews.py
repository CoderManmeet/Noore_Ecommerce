"""
Phase G4: every review that existed before moderation is marked APPROVED, so nothing
vanishes from the storefront. The owner can reject demo ones afterwards.

Reverse sets them back to PENDING (the column itself is dropped by reversing 0037).
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields


MIGRATION_NOTE = "approved by migration 0038"


def approve_existing(apps, schema_editor):
    Review = apps.get_model("store", "Review")
    Review.objects.all().update(status="APPROVED", active=True)


def back_to_pending(apps, schema_editor):
    Review = apps.get_model("store", "Review")
    Review.objects.filter(status="APPROVED", moderated_at__isnull=True).update(status="PENDING")


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0037_review_moderation_fields"),
    ]

    operations = [
        migrations.RunPython(approve_existing, back_to_pending),
    ]
