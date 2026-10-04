from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from catalog.models import ProductVariant
from core.models import AppendOnlyModel


class Channel(models.TextChoices):
    WEBSITE = "WEBSITE", "Website"
    AMAZON = "AMAZON", "Amazon"
    FLIPKART = "FLIPKART", "Flipkart"
    QCOMM = "QCOMM", "Quick commerce"
    OFFLINE = "OFFLINE", "Offline"
    MANUAL = "MANUAL", "Manual"


class MovementKind(models.TextChoices):
    PRODUCTION_IN = "PRODUCTION_IN", "Production in"
    SALE_OUT = "SALE_OUT", "Sale out"
    RETURN_IN = "RETURN_IN", "Customer return in"
    RTO_IN = "RTO_IN", "RTO in"
    DAMAGE_OUT = "DAMAGE_OUT", "Damage / write-off out"
    ADJUSTMENT = "ADJUSTMENT", "Manual adjustment"


# Kinds that must increase stock, and kinds that must decrease it.
INBOUND_KINDS = {MovementKind.PRODUCTION_IN, MovementKind.RETURN_IN, MovementKind.RTO_IN}
OUTBOUND_KINDS = {MovementKind.SALE_OUT, MovementKind.DAMAGE_OUT}
# ADJUSTMENT may be either sign.


class Batch(models.Model):
    """
    A production batch of one variant. The brand manufactures in-house, so batch,
    manufacture date and shelf life are first-class.

    There is deliberately no stored `quantity_remaining` column: remaining quantity is
    derived from the stock ledger (see `quantity_remaining`). A mutable counter would be a
    second source of truth and could drift from the ledger.
    """

    batch_code = models.CharField(max_length=64, unique=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="batches")
    manufactured_on = models.DateField()
    best_before = models.DateField(null=True, blank=True)
    quantity_produced = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    cost_per_unit_paise = models.BigIntegerField(validators=[MinValueValidator(0)])
    production_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["best_before", "manufactured_on", "id"]
        verbose_name_plural = "Batches"
        indexes = [models.Index(fields=["variant", "best_before"])]

    def __str__(self):
        return self.batch_code

    @property
    def quantity_remaining(self):
        from inventory.services import batch_on_hand

        return batch_on_hand(self)

    @property
    def is_expired(self):
        return self.best_before is not None and self.best_before < timezone.localdate()


class StockMovement(AppendOnlyModel):
    """
    The single source of truth for stock. Append-only: quantity is signed, positive for
    stock coming in and negative for stock going out. On-hand stock for a variant is the
    sum of its movements; nothing else may store a stock count.
    """

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="movements")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, null=True, blank=True, related_name="movements")
    kind = models.CharField(max_length=20, choices=MovementKind.choices)
    quantity = models.IntegerField(help_text="Signed: positive is stock in, negative is stock out.")
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WEBSITE)
    reason = models.CharField(max_length=255, blank=True)

    # Free-form link back to whatever caused the movement (order item, return, adjustment form).
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_label = models.CharField(max_length=100, default="system")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["variant", "created_at"]),
            models.Index(fields=["batch", "created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.kind} {self.quantity:+d} {self.variant.sku}"


class ReservationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CONSUMED = "CONSUMED", "Consumed"
    RELEASED = "RELEASED", "Released"
    EXPIRED = "EXPIRED", "Expired"


class StockReservation(models.Model):
    """
    A hold on stock from a specific batch, taken when an item enters a cart or an order
    draft and released automatically when it expires.

    Available stock = on-hand (ledger sum) minus ACTIVE reservations.
    """

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="reservations")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE)

    cart_id = models.CharField(max_length=1000, blank=True, db_index=True)
    order = models.ForeignKey(
        "store.CartOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_reservations"
    )
    order_item = models.ForeignKey(
        "store.CartOrderItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_reservations"
    )

    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "expires_at"]), models.Index(fields=["variant", "status"])]

    def __str__(self):
        return f"{self.quantity} x {self.variant.sku} from {self.batch.batch_code} [{self.status}]"
