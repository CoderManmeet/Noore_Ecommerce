"""
Phase G1: the store sells in Indian rupees.

Sets ConfigSettings.currency_sign to the rupee sign and currency_abbreviation to INR on
every existing row. Reverse restores "$" / "USD".

The model-level defaults ("$", "USD") are deliberately left alone here; changing them is a
schema change and has its own migration (0005).
"""

from django.db import migrations

RUPEE = "\u20b9"


def to_inr(apps, schema_editor):
    ConfigSettings = apps.get_model("addon", "ConfigSettings")
    ConfigSettings.objects.all().update(currency_sign=RUPEE, currency_abbreviation="INR")


def to_usd(apps, schema_editor):
    ConfigSettings = apps.get_model("addon", "ConfigSettings")
    ConfigSettings.objects.all().update(currency_sign="$", currency_abbreviation="USD")


class Migration(migrations.Migration):

    dependencies = [
        ("addon", "0003_configsettings_pricing_fields"),
    ]

    operations = [
        migrations.RunPython(to_inr, to_usd),
    ]
