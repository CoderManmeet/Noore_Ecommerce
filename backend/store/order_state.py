"""
Order state machine.

Before this module, order status was three independent free-text fields that no code path
ever changed except the payment view. Every status change now goes through here, which:

  * rejects transitions that are not allowed,
  * enforces that a COD order cannot be dispatched before it is confirmed (Feature 1),
  * moves stock through inventory.services at the right moments,
  * writes an audit row for every change.

The existing status VALUES are unchanged, so existing rows, the admin and the frontend
keep working. This module constrains how they may change, it does not rename them.
"""

import logging

from django.db import transaction

from core.audit import record
from inventory.models import Channel
from inventory.services import consume_for_order, hold_for_order, release_for_order

logger = logging.getLogger(__name__)


class OrderStateError(Exception):
    """A requested order transition is not allowed."""


class CODNotConfirmed(OrderStateError):
    """A COD order cannot be dispatched until the customer confirms it."""


# --- payment_status ------------------------------------------------------------------
PAYMENT_TRANSITIONS = {
    "initiated": {"processing", "pending", "failed", "cancelled", "expired"},
    "processing": {"paid", "pending", "failed", "cancelled", "expired"},
    "pending": {"paid", "failed", "cancelled", "expired"},
    "paid": {"refunding", "refunded"},
    "failed": {"processing", "cancelled", "expired"},
    "unpaid": {"processing", "paid", "cancelled", "expired"},
    "refunding": {"refunded"},
    "refunded": set(),
    "cancelled": set(),
    "expired": set(),
}

# --- order_status --------------------------------------------------------------------
ORDER_TRANSITIONS = {
    "Pending": {"Fulfilled", "Partially Fulfilled", "Cancelled"},
    "Partially Fulfilled": {"Fulfilled", "Cancelled"},
    "Fulfilled": {"Cancelled"},
    "Cancelled": set(),
}

# --- delivery_status (per order item) ------------------------------------------------
DELIVERY_TRANSITIONS = {
    "On Hold": {"Shipping Processing", "Returning"},
    "Shipping Processing": {"Shipped", "On Hold", "Returning"},
    "Shipped": {"Arrived", "Returning"},
    "Arrived": {"Delivered", "Returning"},
    "Delivered": {"Returning"},
    "Returning": {"Returned"},
    "Returned": set(),
}

# Reaching any of these means the parcel has left the building.
DISPATCH_STATUSES = {"Shipping Processing", "Shipped", "Arrived", "Delivered"}

# Payment states in which stock should be given back.
STOCK_RELEASING_PAYMENT_STATES = {"cancelled", "failed", "expired", "refunded"}


def _check(transitions, current, target, label):
    if current == target:
        return False
    allowed = transitions.get(current)
    if allowed is None:
        raise OrderStateError(f"Unknown {label} {current!r}.")
    if target not in allowed:
        raise OrderStateError(f"{label} cannot go from {current!r} to {target!r}.")
    return True


def can_dispatch(order):
    """
    True when this order may physically leave. A COD order must be confirmed first.

    `cod_confirmed_at` does not exist yet (it arrives with Feature 1); until then the
    check reads it defensively so this module works before and after that migration.
    """
    if (order.payment_method or "").upper() != "COD":
        return True
    return getattr(order, "cod_confirmed_at", None) is not None


@transaction.atomic
def set_payment_status(order, target, reason="", actor=None):
    """Move an order's payment status, releasing stock when the order dies."""
    from store.models import CartOrder

    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    current = order.payment_status
    if not _check(PAYMENT_TRANSITIONS, current, target, "payment_status"):
        return order

    order.payment_status = target
    order.save(update_fields=["payment_status"])

    if target in STOCK_RELEASING_PAYMENT_STATES:
        release_for_order(order, reason=f"payment {target}")

    record("order.payment_status", order, before={"payment_status": current},
           after={"payment_status": target}, reason=reason, actor=actor)

    if target == "paid":
        # Checkout holds expire after a few minutes; a paid order's stock must not.
        shortfalls = hold_for_order(order, reason=reason or "order paid")
        for item, missing in shortfalls:
            record("order.stock_shortfall", order, before=None,
                   after={"order_item": item.pk, "variant": item.variant.sku, "missing_qty": missing},
                   reason="paid, but stock could not be held; resolve before dispatch", actor=actor)
        if shortfalls and (order.payment_method or "").upper() != "COD":
            # Money was taken for something that can no longer be shipped in full. The order is
            # flagged so the owner refunds or restocks; it is never left looking shippable.
            note = "Paid, but stock ran out before payment arrived. Refund or restock before dispatch."
            CartOrder.objects.filter(pk=order.pk).update(needs_attention=note)
            order.needs_attention = note
    return order


@transaction.atomic
def set_order_status(order, target, reason="", actor=None):
    """Move an order's fulfilment status."""
    from store.models import CartOrder

    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    current = order.order_status
    if not _check(ORDER_TRANSITIONS, current, target, "order_status"):
        return order

    order.order_status = target
    order.save(update_fields=["order_status"])

    if target == "Cancelled":
        release_for_order(order, reason="order cancelled")

    record("order.order_status", order, before={"order_status": current},
           after={"order_status": target}, reason=reason, actor=actor)
    return order


@transaction.atomic
def set_delivery_status(order_item, target, reason="", actor=None, channel=Channel.WEBSITE):
    """
    Move one order item through fulfilment.

    Crossing into dispatch consumes the order's stock reservations (stock physically
    leaves) and is blocked for unconfirmed COD orders.
    """
    from store.models import CartOrderItem

    order_item = CartOrderItem.objects.select_for_update().get(pk=order_item.pk)
    current = order_item.delivery_status
    if not _check(DELIVERY_TRANSITIONS, current, target, "delivery_status"):
        return order_item

    order = order_item.order
    entering_dispatch = target in DISPATCH_STATUSES and current not in DISPATCH_STATUSES
    if entering_dispatch and not can_dispatch(order):
        raise CODNotConfirmed(
            f"Order {order.oid} is Cash on Delivery and has not been confirmed by the customer yet."
        )

    order_item.delivery_status = target
    # Keep the existing stage booleans in step so the current UI stays correct.
    if target == "Shipping Processing":
        order_item.processing_order = True
    elif target == "Shipped":
        order_item.product_shipped = True
    elif target == "Arrived":
        order_item.product_arrived = True
    elif target == "Delivered":
        order_item.product_delivered = True
    order_item.save()

    if entering_dispatch:
        consume_for_order(order, channel=channel, reason=f"dispatch: {target}")

    record("order_item.delivery_status", order_item, before={"delivery_status": current},
           after={"delivery_status": target}, reason=reason, actor=actor)
    return order_item


@transaction.atomic
def cancel_order(order, reason="cancelled", actor=None):
    """Cancel an order and give all held stock back. Safe to call twice."""
    from store.models import CartOrder

    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    if order.order_status != "Cancelled":
        set_order_status(order, "Cancelled", reason=reason, actor=actor)
        order.refresh_from_db()
    if order.payment_status in PAYMENT_TRANSITIONS and "cancelled" in PAYMENT_TRANSITIONS[order.payment_status]:
        set_payment_status(order, "cancelled", reason=reason, actor=actor)
    else:
        release_for_order(order, reason=reason)
    return order


class StockUnavailable(OrderStateError):
    """The order's stock could not be held."""


@transaction.atomic
def place_cod_order(order, reason="customer chose cash on delivery", actor=None):
    """
    Place an order draft as Cash on Delivery.

    The order moves to payment_status "pending" (awaiting cash), its stock holds are pinned so
    the checkout TTL no longer applies, and nothing is charged. If the stock is no longer
    there the whole step is rolled back and StockUnavailable is raised: no money has changed
    hands, so the customer is simply told. Safe to call twice.
    """
    from store.models import CartOrder

    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    if order.payment_status == "pending" and (order.payment_method or "").upper() == "COD":
        return order
    if order.payment_status not in ("initiated", "processing") or order.order_status == "Cancelled":
        raise OrderStateError("This order can no longer be placed.")

    before = {"payment_method": order.payment_method, "payment_provider": order.payment_provider}
    order.payment_method = "COD"
    order.payment_provider = "cod"
    order.save(update_fields=["payment_method", "payment_provider"])
    record("order.payment_method", order, before=before,
           after={"payment_method": "COD", "payment_provider": "cod"}, reason=reason, actor=actor)

    order = set_payment_status(order, "pending", reason=reason, actor=actor)
    shortfalls = hold_for_order(order, reason="cash on delivery order placed")
    if shortfalls:
        names = ", ".join(item.product.title for item, _missing in shortfalls)
        raise StockUnavailable(f"Sorry, {names} just sold out. Please update your cart.")
    return order


@transaction.atomic
def confirm_cod(order, actor=None, reason="confirmed with the customer"):
    """
    Record that the owner has confirmed a COD order with the customer (by phone or WhatsApp).
    Until this is set, `can_dispatch` refuses to let the order leave. Audited. Safe to call twice.
    """
    from django.utils import timezone

    from store.models import CartOrder

    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    if (order.payment_method or "").upper() != "COD":
        raise OrderStateError("Only a Cash on Delivery order can be confirmed.")
    if order.order_status == "Cancelled" or order.payment_status in ("cancelled", "expired"):
        raise OrderStateError("A cancelled order cannot be confirmed.")
    if order.cod_confirmed_at is not None:
        return order
    order.cod_confirmed_at = timezone.now()
    order.cod_confirmed_by = actor if getattr(actor, "is_authenticated", False) else None
    order.save(update_fields=["cod_confirmed_at", "cod_confirmed_by"])
    record("order.cod_confirmed", order, before={"cod_confirmed_at": None},
           after={"cod_confirmed_at": order.cod_confirmed_at.isoformat()}, reason=reason, actor=actor)
    return order


DELIVERY_PATH = ["On Hold", "Shipping Processing", "Shipped", "Arrived", "Delivered"]


@transaction.atomic
def advance_order_delivery(order, target, actor=None, reason="", tracking_id=None, courier=None):
    """
    Move every line of an order forward to `target` ("Shipping Processing", "Shipped",
    "Arrived" or "Delivered"), one allowed step at a time through set_delivery_status, so the
    COD check and the single stock consumption on dispatch always apply. Lines already at or
    past the target are left alone. When every line is Delivered the order is Fulfilled and
    `delivered_at` is stamped. Returns the refreshed order.
    """
    from django.utils import timezone

    from store.models import CartOrder, CartOrderItem

    if target not in DELIVERY_PATH[1:]:
        raise OrderStateError(f"Delivery status cannot be set to {target!r} here.")
    order = CartOrder.objects.select_for_update().get(pk=order.pk)
    if order.order_status == "Cancelled":
        raise OrderStateError("A cancelled order cannot be shipped.")
    if order.payment_status not in ("paid", "pending"):
        raise OrderStateError("Only a paid or Cash on Delivery order can be shipped.")
    if order.needs_attention:
        raise OrderStateError("This order is flagged for attention. Resolve the flag before shipping it.")

    target_index = DELIVERY_PATH.index(target)
    for item in CartOrderItem.objects.filter(order=order).order_by("id"):
        if item.delivery_status not in DELIVERY_PATH:
            continue  # Returning / Returned lines are not moved forward
        if tracking_id is not None or courier is not None:
            if tracking_id is not None:
                item.tracking_id = tracking_id
            if courier is not None:
                item.delivery_couriers = courier
            item.save(update_fields=["tracking_id", "delivery_couriers"])
        position = DELIVERY_PATH.index(item.delivery_status)
        while position < target_index:
            position += 1
            item = set_delivery_status(item, DELIVERY_PATH[position], reason=reason, actor=actor)

    statuses = set(CartOrderItem.objects.filter(order=order).values_list("delivery_status", flat=True))
    if statuses == {"Delivered"}:
        if order.order_status != "Fulfilled":
            set_order_status(order, "Fulfilled", reason="all lines delivered", actor=actor)
        if order.delivered_at is None:
            CartOrder.objects.filter(pk=order.pk).update(delivered_at=timezone.now())
    order.refresh_from_db()
    return order


def mark_paid(order, reason="payment verified", actor=None):
    """Convenience wrapper used by the payment views."""
    return set_payment_status(order, "paid", reason=reason, actor=actor)
