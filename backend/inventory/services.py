"""
Stock services. Every read and write of stock goes through this module.

Rules enforced here:
  * On-hand stock is the sum of `StockMovement.quantity`. Nothing stores a stock count.
  * Available = on-hand minus ACTIVE reservations.
  * Allocation is FEFO by default (first expiry first out), FIFO when configured.
  * A batch whose best_before falls inside MIN_SHELF_LIFE_ON_DISPATCH_DAYS is never
    auto-allocated, and an expired batch is never allocated at all.
  * Allocation locks the variant row, so two concurrent checkouts for the last unit
    cannot both succeed (real row locking requires PostgreSQL).
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.audit import get_actor, record
from inventory.models import (
    Batch,
    Channel,
    MovementKind,
    OUTBOUND_KINDS,
    INBOUND_KINDS,
    ReservationStatus,
    StockMovement,
    StockReservation,
)

logger = logging.getLogger(__name__)


class StockError(Exception):
    """Base class for stock problems."""


class InsufficientStock(StockError):
    def __init__(self, variant, requested, available):
        self.variant = variant
        self.requested = requested
        self.available = available
        super().__init__(f"Only {available} of {variant.sku} available, {requested} requested.")


class InvalidMovement(StockError):
    pass


# --------------------------------------------------------------------------- reads

def on_hand_qty(variant):
    """Physical stock of a variant across all batches, from the ledger."""
    return StockMovement.objects.filter(variant=variant).aggregate(total=Sum("quantity"))["total"] or 0


def batch_on_hand(batch):
    """Physical stock remaining in one batch, from the ledger."""
    return StockMovement.objects.filter(batch=batch).aggregate(total=Sum("quantity"))["total"] or 0


def reserved_qty(variant):
    """Units currently held by ACTIVE, unexpired reservations."""
    return (
        StockReservation.objects.filter(
            variant=variant, status=ReservationStatus.ACTIVE, expires_at__gt=timezone.now()
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )


def batch_reserved_qty(batch):
    return (
        StockReservation.objects.filter(
            batch=batch, status=ReservationStatus.ACTIVE, expires_at__gt=timezone.now()
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )


def available_qty(variant):
    """What a shopper may still buy."""
    return max(on_hand_qty(variant) - reserved_qty(variant), 0)


def min_shelf_life_cutoff():
    """Batches expiring on or before this date must not be auto-allocated."""
    days = settings.MIN_SHELF_LIFE_ON_DISPATCH_DAYS
    return timezone.localdate() + timedelta(days=days)


def allocatable_batches(variant, strategy=None):
    """
    Batches this variant may be allocated from, in allocation order.

    Excludes batches that are expired or inside the minimum-shelf-life window, and
    batches with nothing left after existing reservations.
    """
    strategy = (strategy or settings.STOCK_ALLOCATION_STRATEGY).upper()
    queryset = Batch.objects.filter(variant=variant)

    cutoff = min_shelf_life_cutoff()
    queryset = queryset.filter(best_before__isnull=True) | queryset.filter(best_before__gt=cutoff)

    if strategy == "FIFO":
        ordered = queryset.order_by("manufactured_on", "id")
    else:  # FEFO: soonest expiry first; batches with no expiry go last.
        ordered = queryset.extra(select={"_bb_null": "best_before IS NULL"}).order_by(
            "_bb_null", "best_before", "manufactured_on", "id"
        )

    result = []
    for batch in ordered:
        free = batch_on_hand(batch) - batch_reserved_qty(batch)
        if free > 0:
            result.append((batch, free))
    return result


# --------------------------------------------------------------------------- writes

def record_movement(variant, kind, quantity, batch=None, channel=Channel.WEBSITE, reason="",
                    reference_type="", reference_id="", actor=None, actor_label=None):
    """
    Append one movement to the ledger.

    `quantity` is signed. Inbound kinds must be positive, outbound kinds negative;
    ADJUSTMENT may be either. Zero is never a movement.
    """
    if quantity == 0:
        raise InvalidMovement("A stock movement cannot be zero.")
    if kind in INBOUND_KINDS and quantity < 0:
        raise InvalidMovement(f"{kind} must be a positive quantity.")
    if kind in OUTBOUND_KINDS and quantity > 0:
        raise InvalidMovement(f"{kind} must be a negative quantity.")
    if kind in (MovementKind.PRODUCTION_IN,) and batch is None:
        raise InvalidMovement("Production must be recorded against a batch.")
    if batch is not None and batch.variant_id != variant.pk:
        raise InvalidMovement("Batch belongs to a different variant.")

    ctx_actor, ctx_label = get_actor()
    movement = StockMovement.objects.create(
        variant=variant,
        batch=batch,
        kind=kind,
        quantity=quantity,
        channel=channel,
        reason=reason[:255],
        reference_type=reference_type[:50],
        reference_id=str(reference_id)[:64],
        actor=actor if actor is not None else ctx_actor,
        actor_label=(actor_label or ctx_label)[:100],
    )
    record(
        "stock.movement",
        movement,
        before=None,
        after={
            "variant": variant.sku,
            "batch": batch.batch_code if batch else None,
            "kind": kind,
            "quantity": quantity,
            "channel": channel,
        },
        reason=reason,
    )
    return movement


def receive_production(variant, batch, quantity, reason="Production received", actor=None):
    """Book a finished production run into stock."""
    return record_movement(
        variant, MovementKind.PRODUCTION_IN, abs(int(quantity)), batch=batch,
        channel=Channel.MANUAL, reason=reason, reference_type="batch", reference_id=batch.pk, actor=actor,
    )


@transaction.atomic
def reserve(variant, quantity, cart_id="", order=None, order_item=None, ttl_minutes=None, strategy=None):
    """
    Hold `quantity` units of `variant`, splitting across batches in FEFO (or FIFO) order.

    Returns the list of StockReservation rows created. Raises InsufficientStock and rolls
    back if the full quantity cannot be held. The variant row is locked for the duration,
    so concurrent callers are serialised.
    """
    quantity = int(quantity)
    if quantity < 1:
        raise InvalidMovement("Reserved quantity must be at least 1.")

    from catalog.models import ProductVariant

    # Lock the variant row so two checkouts cannot both take the last unit.
    variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)

    expire_due_reservations()

    available = available_qty(variant)
    if available < quantity:
        raise InsufficientStock(variant, quantity, available)

    expires_at = timezone.now() + timedelta(minutes=ttl_minutes or settings.STOCK_RESERVATION_TTL_MINUTES)

    remaining = quantity
    reservations = []
    for batch, free in allocatable_batches(variant, strategy=strategy):
        if remaining <= 0:
            break
        take = min(free, remaining)
        reservations.append(
            StockReservation.objects.create(
                variant=variant, batch=batch, quantity=take, cart_id=cart_id or "",
                order=order, order_item=order_item, expires_at=expires_at,
            )
        )
        remaining -= take

    if remaining > 0:
        # Stock exists on hand but is not allocatable (expired or inside the shelf-life window).
        raise InsufficientStock(variant, quantity, quantity - remaining)

    return reservations


@transaction.atomic
def release(reservations, reason="released"):
    """Give held stock back. Only ACTIVE reservations change."""
    if isinstance(reservations, StockReservation):
        reservations = [reservations]
    count = 0
    for reservation in reservations:
        updated = StockReservation.objects.filter(pk=reservation.pk, status=ReservationStatus.ACTIVE).update(
            status=ReservationStatus.RELEASED, resolved_at=timezone.now()
        )
        count += updated
    if count:
        logger.info("released %s stock reservation(s): %s", count, reason)
    return count


@transaction.atomic
def release_for_cart(cart_id, reason="cart released"):
    reservations = StockReservation.objects.filter(cart_id=cart_id, status=ReservationStatus.ACTIVE)
    return release(list(reservations), reason=reason)


@transaction.atomic
def release_for_order(order, reason="order cancelled"):
    reservations = StockReservation.objects.filter(order=order, status=ReservationStatus.ACTIVE)
    return release(list(reservations), reason=reason)


@transaction.atomic
def attach_reservations_to_order(cart_id, order, item_by_variant=None):
    """Move a cart's holds onto the order created from it."""
    item_by_variant = item_by_variant or {}
    moved = 0
    for reservation in StockReservation.objects.filter(cart_id=cart_id, status=ReservationStatus.ACTIVE):
        reservation.order = order
        reservation.order_item = item_by_variant.get(reservation.variant_id)
        reservation.save(update_fields=["order", "order_item"])
        moved += 1
    return moved


# A paid order's holds must outlive the checkout TTL: they are only ever resolved by dispatch
# (consume_for_order) or by cancellation (release_for_order).
PAID_HOLD_DAYS = 3650


@transaction.atomic
def hold_for_order(order, reason="order paid"):
    """
    Secure the stock of an order that has just been paid for.

    * Holds that are still ACTIVE are pinned so the reservation-expiry job never returns
      them to the shelf.
    * If a hold already lapsed (the customer paid after the checkout TTL), the shortfall is
      reserved again, as long as the stock is still there.

    Idempotent. Returns a list of (order_item, missing_qty) for lines that could not be fully
    held, so the caller can flag the order for the owner; it never raises for a shortfall,
    because the customer's payment has already been taken.
    """
    from store.models import CartOrderItem

    pinned_until = timezone.now() + timedelta(days=PAID_HOLD_DAYS)
    StockReservation.objects.filter(
        order=order, status=ReservationStatus.ACTIVE, expires_at__gt=timezone.now()
    ).update(expires_at=pinned_until)

    shortfalls = []
    for item in CartOrderItem.objects.filter(order=order).select_related("variant"):
        if item.variant_id is None or item.qty < 1:
            continue
        held = (
            StockReservation.objects.filter(
                order=order, variant=item.variant, status__in=[ReservationStatus.ACTIVE, ReservationStatus.CONSUMED],
            ).exclude(status=ReservationStatus.ACTIVE, expires_at__lte=timezone.now())
            .aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        missing = item.qty - held
        if missing <= 0:
            continue
        try:
            with transaction.atomic():
                reserve(item.variant, missing, order=order, order_item=item, ttl_minutes=PAID_HOLD_DAYS * 24 * 60)
        except InsufficientStock:
            shortfalls.append((item, missing))
            logger.warning("order %s paid but %s unit(s) of %s could not be held", order.pk, missing, item.variant.sku)
    if not shortfalls:
        logger.info("stock secured for paid order %s: %s", order.pk, reason)
    return shortfalls


@transaction.atomic
def consume_for_order(order, channel=Channel.WEBSITE, reason="dispatched"):
    """
    Turn an order's holds into SALE_OUT movements: stock physically leaves.

    Idempotent: reservations already CONSUMED are skipped, so calling this twice for the
    same order never decrements stock twice.
    """
    reservations = list(
        StockReservation.objects.select_for_update().filter(order=order, status=ReservationStatus.ACTIVE)
    )
    movements = []
    for reservation in reservations:
        updated = StockReservation.objects.filter(pk=reservation.pk, status=ReservationStatus.ACTIVE).update(
            status=ReservationStatus.CONSUMED, resolved_at=timezone.now()
        )
        if not updated:
            continue
        movements.append(
            record_movement(
                reservation.variant,
                MovementKind.SALE_OUT,
                -reservation.quantity,
                batch=reservation.batch,
                channel=channel,
                reason=reason,
                reference_type="order",
                reference_id=order.pk,
            )
        )
    return movements


@transaction.atomic
def expire_due_reservations():
    """Return stock held by reservations whose time is up. Returns the count."""
    return StockReservation.objects.filter(
        status=ReservationStatus.ACTIVE, expires_at__lte=timezone.now()
    ).update(status=ReservationStatus.EXPIRED, resolved_at=timezone.now())


# --------------------------------------------------------------------------- reporting

def batches_nearing_expiry(days=None):
    """Batches with stock left that expire within `days` (default EXPIRY_ALERT_DAYS)."""
    days = days if days is not None else settings.EXPIRY_ALERT_DAYS
    today = timezone.localdate()
    horizon = today + timedelta(days=days)
    result = []
    for batch in Batch.objects.filter(best_before__isnull=False, best_before__gte=today, best_before__lte=horizon):
        remaining = batch_on_hand(batch)
        if remaining > 0:
            result.append((batch, remaining))
    return result


def expired_unsold_batches():
    """Batches already past best_before that still have stock on hand."""
    today = timezone.localdate()
    result = []
    for batch in Batch.objects.filter(best_before__isnull=False, best_before__lt=today):
        remaining = batch_on_hand(batch)
        if remaining > 0:
            result.append((batch, remaining))
    return result


def reconcile_batch(batch):
    """
    Consistency check used by tests and the owner dashboard:
    produced - sold - written off + returned == on hand.
    """
    movements = StockMovement.objects.filter(batch=batch)
    produced = movements.filter(kind=MovementKind.PRODUCTION_IN).aggregate(t=Sum("quantity"))["t"] or 0
    returned = movements.filter(kind__in=[MovementKind.RETURN_IN, MovementKind.RTO_IN]).aggregate(t=Sum("quantity"))["t"] or 0
    sold = movements.filter(kind=MovementKind.SALE_OUT).aggregate(t=Sum("quantity"))["t"] or 0
    damaged = movements.filter(kind=MovementKind.DAMAGE_OUT).aggregate(t=Sum("quantity"))["t"] or 0
    adjusted = movements.filter(kind=MovementKind.ADJUSTMENT).aggregate(t=Sum("quantity"))["t"] or 0
    return {
        "produced": produced,
        "returned": returned,
        "sold": sold,
        "damaged": damaged,
        "adjusted": adjusted,
        "on_hand": batch_on_hand(batch),
        "balances": produced + returned + sold + damaged + adjusted == batch_on_hand(batch),
    }
