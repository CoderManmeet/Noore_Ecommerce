"""
Backfill one default ProductVariant for every existing Product.

Reversible: the reverse operation deletes only the variants this migration created
(name="Default", is_default=True) and only when nothing references them.
"""

from django.db import migrations


def _sku_for(product, taken):
    base = (product.sku or f"PID-{product.pid}" or f"PRODUCT-{product.pk}").strip()[:56]
    candidate = base or f"PRODUCT-{product.pk}"
    suffix = 1
    while candidate in taken:
        suffix += 1
        candidate = f"{base[:56]}-{suffix}"
    taken.add(candidate)
    return candidate


def create_default_variants(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    ProductVariant = apps.get_model("catalog", "ProductVariant")

    taken = set(ProductVariant.objects.values_list("sku", flat=True))
    new_variants = []
    for product in Product.objects.filter(variants__isnull=True).iterator():
        price = product.price or 0
        mrp = product.old_price or None
        new_variants.append(
            ProductVariant(
                product=product,
                sku=_sku_for(product, taken),
                name="Default",
                price_paise=int(round(float(price) * 100)),
                mrp_paise=int(round(float(mrp) * 100)) if mrp else None,
                is_default=True,
                active=(product.status == "published"),
            )
        )
    ProductVariant.objects.bulk_create(new_variants, batch_size=500)


def remove_default_variants(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    # Only variants this migration created, and only when nothing references them.
    # Batches are not filtered here because inventory.Batch does not exist in this
    # migration's historical state; its PROTECT foreign key raises instead of deleting,
    # which is why inventory must be rolled back before catalog.
    ProductVariant.objects.filter(
        name="Default", is_default=True, order_items__isnull=True, cart_items__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("store", "0028_variant_channel_cod_fields"),
    ]

    operations = [
        migrations.RunPython(create_default_variants, remove_default_variants),
    ]
