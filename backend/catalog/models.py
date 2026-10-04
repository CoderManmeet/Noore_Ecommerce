from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import AppendOnlyModel
from store.models import Product


class ProductVariant(models.Model):
    """
    A sellable unit: the thing that carries a SKU, a price and stock.

    `Product` remains the marketing/catalogue entry. Every product has exactly one
    default variant (created by the F-B backfill); products with real options get more.
    Money is stored as integer paise (rule 6). Legacy Decimal columns on Product are
    left untouched and remain the source of truth until the money migration.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120, default="Default")

    # Optional option values. Kept as plain text to mirror how the cart already stores them.
    size = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=100, blank=True)

    # What makes this variant different from its siblings, as {option name: value}, e.g.
    # {"Size": "200 g"}. The storefront builds one selector per key, so a second axis
    # (for example {"Size": "200 g", "Colour": "Ivory"}) needs data only, no code.
    options = models.JSONField(default=dict, blank=True)

    price_paise = models.BigIntegerField(validators=[MinValueValidator(0)])
    mrp_paise = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])

    weight_grams = models.PositiveIntegerField(null=True, blank=True)

    # Perishable variants require a best_before on every batch and show it on the product page.
    perishable = models.BooleanField(default=False)

    is_default = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id", "-is_default", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"], condition=models.Q(is_default=True), name="catalog_one_default_variant_per_product"
            ),
        ]

    def __str__(self):
        return f"{self.sku} ({self.product.title} / {self.name})"

    @property
    def available_qty(self):
        from inventory.services import available_qty

        return available_qty(self)


class PriceHistory(AppendOnlyModel):
    """
    Append-only record of every selling price and MRP a variant has had (ROADMAP P9).

    One row is written by a signal each time `ProductVariant.price_paise` or `mrp_paise`
    changes through save(), whatever the entry point (owner dashboard, Django admin, shell,
    management command). `effective_from` is when that price started applying; a row stays
    in force until the next row for the same variant.
    """

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="price_history")
    price_paise = models.BigIntegerField(validators=[MinValueValidator(0)])
    mrp_paise = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    effective_from = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        "userauths.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_label = models.CharField(max_length=100, default="system")

    class Meta:
        ordering = ["-effective_from", "-id"]
        verbose_name_plural = "Price history"
        indexes = [models.Index(fields=["variant", "effective_from"])]

    def __str__(self):
        return f"{self.variant.sku} @ {self.price_paise} paise from {self.effective_from:%Y-%m-%d %H:%M}"
