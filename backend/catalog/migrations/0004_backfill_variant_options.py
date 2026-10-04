"""
Phase G2: fill ProductVariant.options from the existing free-text size / color columns, so
any variant that already had them shows up in the generic picker. The size and color
columns are left exactly as they are.

Reverse empties only the options this migration could have written (those that equal the
size/color-derived value); options edited since are left alone.
"""

from django.db import migrations


def _derived(variant):
    options = {}
    if (variant.size or "").strip():
        options["Size"] = variant.size.strip()
    if (variant.color or "").strip():
        options["Colour"] = variant.color.strip()
    return options


def fill_options(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    for variant in ProductVariant.objects.all().iterator():
        if variant.options:
            continue
        options = _derived(variant)
        if options:
            variant.options = options
            variant.save(update_fields=["options"])


def clear_options(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    for variant in ProductVariant.objects.all().iterator():
        if variant.options and variant.options == _derived(variant):
            variant.options = {}
            variant.save(update_fields=["options"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_productvariant_options"),
    ]

    operations = [
        migrations.RunPython(fill_options, clear_options),
    ]
