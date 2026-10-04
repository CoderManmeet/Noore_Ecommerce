"""
Catalogue signals.

Product <-> default variant (Phase G1)
    `ProductVariant.price_paise` is the only source of a selling price (ROADMAP P7), but the
    owner dashboard and Django admin still edit `Product.price` / `Product.old_price`. These
    handlers keep the two in step in both directions, from every entry point:

      * a new Product gets its default variant (and, when it was created with a stock
        quantity, an opening batch in the stock ledger);
      * changing Product.price or Product.old_price writes the default variant's
        price_paise / mrp_paise;
      * changing the default variant's price writes the legacy Product columns back as a
        mirror (ROADMAP A5), so nothing shows a stale number.

Price history (Phase G2)
    Every change of `ProductVariant.price_paise` or `mrp_paise` made through save() writes
    exactly one append-only `PriceHistory` row with the actor, whatever the entry point.
    (queryset.update() and raw SQL bypass signals and are therefore not recorded; nothing in
    this codebase changes a price that way.)
"""

import logging

from django.db.models.signals import post_init, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from catalog.models import PriceHistory, ProductVariant
from core.audit import get_actor
from core.money import from_paise
from store.models import Product
from store.money_mirror import decimal_to_paise

logger = logging.getLogger(__name__)

OPENING_STOCK_REASON = "Opening stock entered when the product was created"


def _unique_sku(product):
    base = (str(product.sku or "") or f"PRODUCT-{product.pk}").strip()[:56]
    candidate = base
    suffix = 1
    while ProductVariant.objects.filter(sku=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _product_prices(product):
    price_paise = decimal_to_paise(product.price)
    mrp_paise = decimal_to_paise(product.old_price)
    return price_paise, (mrp_paise if mrp_paise > 0 else None)


def _create_default_variant(product):
    from inventory.models import Batch, Channel, MovementKind
    from inventory.services import record_movement

    price_paise, mrp_paise = _product_prices(product)
    variant = ProductVariant.objects.create(
        product=product,
        sku=_unique_sku(product),
        name="Default",
        price_paise=price_paise,
        mrp_paise=mrp_paise,
        is_default=True,
        active=True,
    )
    quantity = int(product.stock_qty or 0)
    if quantity > 0:
        batch = Batch.objects.create(
            batch_code=f"OPENING-{variant.sku}"[:64],
            variant=variant,
            manufactured_on=timezone.localdate(),
            best_before=None,
            quantity_produced=quantity,
            cost_per_unit_paise=0,
            production_notes=OPENING_STOCK_REASON,
        )
        record_movement(
            variant, MovementKind.ADJUSTMENT, quantity, batch=batch, channel=Channel.MANUAL,
            reason=OPENING_STOCK_REASON, reference_type="product", reference_id=product.pk,
        )
    return variant


def _current_prices(product):
    return decimal_to_paise(product.price), decimal_to_paise(product.old_price)


@receiver(post_init, sender=Product, dispatch_uid="catalog_product_remember_prices")
def remember_product_prices(sender, instance, **kwargs):
    """
    Remember the prices this instance was loaded with, so a save can tell "the owner edited
    the price" apart from "an instance loaded earlier was saved for some other reason".
    """
    if instance.pk is None or "price" in instance.get_deferred_fields() or "old_price" in instance.get_deferred_fields():
        instance._catalog_loaded_prices = None
    else:
        instance._catalog_loaded_prices = _current_prices(instance)


@receiver(post_save, sender=Product, dispatch_uid="catalog_product_sync_default_variant")
def sync_default_variant(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    default = ProductVariant.objects.filter(product=instance, is_default=True).first()
    if default is None:
        if not ProductVariant.objects.filter(product=instance).exists():
            _create_default_variant(instance)
        instance._catalog_loaded_prices = _current_prices(instance)
        return

    loaded = getattr(instance, "_catalog_loaded_prices", None)
    current = _current_prices(instance)

    if loaded is not None and loaded != current:
        # The price was edited on the product (owner dashboard, Django admin): the default
        # variant follows, field by field.
        price_paise, mrp_paise = _product_prices(instance)
        changed = []
        if loaded[0] != current[0] and default.price_paise != price_paise:
            default.price_paise = price_paise
            changed.append("price_paise")
        if loaded[1] != current[1] and default.mrp_paise != mrp_paise:
            default.mrp_paise = mrp_paise
            changed.append("mrp_paise")
        if changed:
            default.save(update_fields=changed + ["updated_at"])

    # Whatever was just written, the legacy columns end up equal to the variant (A5). This
    # also repairs a stale instance that was saved for an unrelated reason.
    _mirror_variant_onto_product(default, instance)


def _mirror_variant_onto_product(variant, product=None):
    price = from_paise(int(variant.price_paise))
    old_price = from_paise(int(variant.mrp_paise or 0))
    # queryset.update(): a mirror write must not re-enter the Product signals above.
    Product.objects.filter(pk=variant.product_id).exclude(price=price, old_price=old_price).update(
        price=price, old_price=old_price
    )
    if product is not None:
        product.price = price
        product.old_price = old_price
        product._catalog_loaded_prices = _current_prices(product)


@receiver(post_save, sender=ProductVariant, dispatch_uid="catalog_variant_mirror_product_price")
def mirror_default_variant_price(sender, instance, **kwargs):
    """Keep the legacy Product.price / old_price columns equal to the default variant (A5)."""
    if kwargs.get("raw") or not instance.is_default:
        return
    _mirror_variant_onto_product(instance)


PRICE_FIELDS = ("price_paise", "mrp_paise")


@receiver(pre_save, sender=ProductVariant, dispatch_uid="catalog_variant_remember_stored_price")
def remember_stored_variant_price(sender, instance, update_fields=None, **kwargs):
    """Note the price currently in the database, to compare with what this save writes."""
    instance._price_history_previous = None
    instance._price_history_skip = False
    if kwargs.get("raw"):
        instance._price_history_skip = True
        return
    if instance.pk is None:
        return
    if update_fields is not None and not set(PRICE_FIELDS) & set(update_fields):
        # This save does not write either price column, so the stored price cannot change.
        instance._price_history_skip = True
        return
    stored = ProductVariant.objects.filter(pk=instance.pk).values(*PRICE_FIELDS).first()
    if stored is not None:
        instance._price_history_previous = (stored["price_paise"], stored["mrp_paise"])


@receiver(post_save, sender=ProductVariant, dispatch_uid="catalog_variant_write_price_history")
def write_price_history(sender, instance, created, update_fields=None, **kwargs):
    if kwargs.get("raw") or getattr(instance, "_price_history_skip", False):
        return
    previous = getattr(instance, "_price_history_previous", None)
    written = [instance.price_paise, instance.mrp_paise]
    if not created and previous is not None and update_fields is not None:
        # Only the columns named in update_fields were actually written.
        for index, name in enumerate(PRICE_FIELDS):
            if name not in update_fields:
                written[index] = previous[index]
    current = tuple(written)
    if not created and previous == current:
        return
    actor, label = get_actor()
    PriceHistory.objects.create(
        variant=instance,
        price_paise=current[0],
        mrp_paise=current[1],
        effective_from=timezone.now(),
        actor=actor,
        actor_label=(label or "system")[:100],
    )
    instance._price_history_previous = current
