"""
Pricing: the ONLY place a customer-facing total is computed.

The cart view, the checkout view, order creation, the coupon endpoint and (from G3) the
payment step all call `quote()`. Nothing else may add up a cart or an order.

Rules (docs/ROADMAP.md, phase G1; decisions P1-P8, A3, A4):

  * Everything is integer paise. No Decimal and no float in here.
  * Unit price is `variant.price_paise`, read when quote() is called (an order line being
    re-quoted passes its stored snapshot price instead, so an existing order never moves
    when the catalogue price changes).
  * subtotal = sum(unit price x qty).
  * A coupon discounts the whole item subtotal, never a single line. PERCENT rounds down to
    a whole paisa; FLAT is capped at the subtotal. The discount is split across the lines in
    proportion to their subtotal (largest remainder), so line totals always sum to
    subtotal - discount to the paisa.
  * Shipping is one flat charge per order, free when subtotal - discount reaches the
    threshold (>=). An empty cart has no shipping.
  * Prices are tax-inclusive. Tax is carved OUT of the amount (amount x rate / (10000 + rate),
    rate in basis points), never added on top. With tax_rate_bps = 0 the tax is 0.
  * total = subtotal - discount + shipping. No service fee. No COD fee.
  * An invalid coupon never raises: the quote comes back without a discount, with
    `coupon_error` (a stable code) and `coupon_message` (text the UI can show).
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.db.models import Q
from django.utils import timezone

from core.money import format_inr
from core.phone import try_to_e164

logger = logging.getLogger(__name__)

DEFAULT_SHIPPING_FLAT_PAISE = 7900
DEFAULT_FREE_SHIPPING_THRESHOLD_PAISE = 99900
DEFAULT_TAX_RATE_BPS = 0

# An order in one of these states no longer holds its coupon use.
DEAD_ORDER_STATUS = "Cancelled"
DEAD_PAYMENT_STATUSES = ("cancelled", "expired")

# Coupon refusal codes (stable; the frontend may switch on them).
COUPON_NOT_FOUND = "not_found"
COUPON_NOT_STARTED = "not_started"
COUPON_EXPIRED = "expired"
COUPON_UNDER_MINIMUM = "under_minimum"
COUPON_TOTAL_CAP = "total_cap_reached"
COUPON_CUSTOMER_CAP = "customer_cap_reached"


class PricingError(ValueError):
    """quote() was called with something that cannot be priced."""


@dataclass(frozen=True)
class Customer:
    """Who is buying. A signed-in customer has `user`; a guest has email and/or phone."""

    user: object = None
    email: str = ""
    phone_e164: str = ""

    @classmethod
    def build(cls, user=None, email="", phone=""):
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        return cls(user=user, email=normalise_email(email), phone_e164=try_to_e164(phone) if phone else "")


@dataclass(frozen=True)
class PricingConfig:
    shipping_flat_paise: int = DEFAULT_SHIPPING_FLAT_PAISE
    free_shipping_threshold_paise: int = DEFAULT_FREE_SHIPPING_THRESHOLD_PAISE
    tax_rate_bps: int = DEFAULT_TAX_RATE_BPS


@dataclass(frozen=True)
class QuoteLine:
    variant: object
    qty: int
    unit_price_paise: int
    line_subtotal_paise: int
    discount_paise: int
    line_total_paise: int
    tax_paise: int


@dataclass(frozen=True)
class Quote:
    lines: List[QuoteLine] = field(default_factory=list)
    subtotal_paise: int = 0
    discount_paise: int = 0
    shipping_paise: int = 0
    tax_paise: int = 0
    total_paise: int = 0
    coupon: object = None
    coupon_code: str = ""
    coupon_error: str = ""
    coupon_message: str = ""
    shipping_flat_paise: int = DEFAULT_SHIPPING_FLAT_PAISE
    free_shipping_threshold_paise: int = DEFAULT_FREE_SHIPPING_THRESHOLD_PAISE
    amount_to_free_shipping_paise: int = 0
    tax_rate_bps: int = DEFAULT_TAX_RATE_BPS

    @property
    def free_shipping(self):
        return bool(self.lines) and self.shipping_paise == 0

    def as_dict(self):
        """JSON-safe representation. Every money value is integer paise."""
        return {
            "subtotal_paise": self.subtotal_paise,
            "discount_paise": self.discount_paise,
            "shipping_paise": self.shipping_paise,
            "tax_paise": self.tax_paise,
            "total_paise": self.total_paise,
            "coupon_code": self.coupon_code,
            "coupon_error": self.coupon_error,
            "coupon_message": self.coupon_message,
            "free_shipping": self.free_shipping,
            "shipping_flat_paise": self.shipping_flat_paise,
            "free_shipping_threshold_paise": self.free_shipping_threshold_paise,
            "amount_to_free_shipping_paise": self.amount_to_free_shipping_paise,
            "tax_rate_bps": self.tax_rate_bps,
            "tax_inclusive": True,
            "currency": "INR",
            "lines": [
                {
                    "variant_id": line.variant.pk,
                    "qty": line.qty,
                    "unit_price_paise": line.unit_price_paise,
                    "line_subtotal_paise": line.line_subtotal_paise,
                    "discount_paise": line.discount_paise,
                    "line_total_paise": line.line_total_paise,
                    "tax_paise": line.tax_paise,
                }
                for line in self.lines
            ],
        }


# --------------------------------------------------------------------------- helpers

def normalise_email(value):
    return str(value or "").strip().lower()


def get_pricing_config():
    """Shipping and tax settings from ConfigSettings (roadmap defaults when no row exists)."""
    from addon.models import ConfigSettings

    row = ConfigSettings.objects.first()
    if row is None:
        return PricingConfig()
    return PricingConfig(
        shipping_flat_paise=int(row.shipping_flat_paise),
        free_shipping_threshold_paise=int(row.free_shipping_threshold_paise),
        tax_rate_bps=int(row.tax_rate_bps),
    )


def carve_out_tax(inclusive_paise, rate_bps):
    """Tax contained in a tax-inclusive amount, rounded half-up to a whole paisa."""
    if rate_bps <= 0 or inclusive_paise <= 0:
        return 0
    denominator = 10000 + rate_bps
    return (inclusive_paise * rate_bps + denominator // 2) // denominator


def split_discount(discount_paise, line_subtotals):
    """
    Split an order-level discount across lines in proportion to line subtotal, using the
    largest-remainder method so the shares always sum to exactly `discount_paise` (A4).
    """
    total = sum(line_subtotals)
    if discount_paise <= 0 or total <= 0:
        return [0] * len(line_subtotals)
    shares = [discount_paise * subtotal // total for subtotal in line_subtotals]
    remainders = [discount_paise * subtotal % total for subtotal in line_subtotals]
    leftover = discount_paise - sum(shares)
    # Largest remainder first; ties go to the earlier line so the result is deterministic.
    order = sorted(range(len(line_subtotals)), key=lambda i: (-remainders[i], i))
    for index in order[:leftover]:
        shares[index] += 1
    return shares


def find_coupon(code, lock=False):
    """The active coupon with this code (case-insensitive), or None."""
    from store.models import Coupon

    code = str(code or "").strip()
    if not code:
        return None
    queryset = Coupon.objects.filter(code__iexact=code, active=True).order_by("-id")
    if lock:
        queryset = queryset.select_for_update()
    return queryset.first()


def live_redemptions(coupon, exclude_order=None):
    """
    Redemptions that currently count against this coupon's caps.

    A redemption stops counting when its order is cancelled or expired, or when the order no
    longer carries this coupon (it was removed or replaced). The rows themselves are
    append-only and are never deleted.
    """
    from store.models import CouponRedemption

    queryset = (
        CouponRedemption.objects.filter(coupon=coupon, order__coupon_code__iexact=coupon.code)
        .exclude(order__order_status=DEAD_ORDER_STATUS)
        .exclude(order__payment_status__in=DEAD_PAYMENT_STATUSES)
    )
    if exclude_order is not None and getattr(exclude_order, "pk", None):
        queryset = queryset.exclude(order=exclude_order)
    return queryset


def customer_redemptions(coupon, customer, exclude_order=None):
    """
    Live redemptions by this customer: matched by user id when signed in, otherwise by
    normalised email or E.164 phone. Returns None when the customer cannot be identified yet
    (a guest who has not entered contact details), in which case the per-customer cap is
    checked later, when the order is created.
    """
    queryset = live_redemptions(coupon, exclude_order=exclude_order)
    if customer is None:
        return None
    if customer.user is not None:
        return queryset.filter(user=customer.user)
    match = Q()
    if customer.email:
        match |= Q(email=customer.email)
    if customer.phone_e164:
        match |= Q(phone_e164=customer.phone_e164)
    if not match:
        return None
    return queryset.filter(match)


def check_coupon(coupon, subtotal_paise, customer=None, exclude_order=None, now=None):
    """Return ("", "") when the coupon may be used, else (error_code, message)."""
    now = now or timezone.now()
    if coupon is None:
        return COUPON_NOT_FOUND, "This coupon code is not valid."
    if coupon.valid_from is not None and now < coupon.valid_from:
        return COUPON_NOT_STARTED, "This coupon is not active yet."
    if coupon.valid_until is not None and now > coupon.valid_until:
        return COUPON_EXPIRED, "This coupon has expired."
    if subtotal_paise < coupon.min_order_paise:
        return (
            COUPON_UNDER_MINIMUM,
            f"This coupon needs a minimum order of {format_inr(int(coupon.min_order_paise))}.",
        )
    if coupon.max_total_uses is not None:
        if live_redemptions(coupon, exclude_order=exclude_order).count() >= coupon.max_total_uses:
            return COUPON_TOTAL_CAP, "This coupon has been fully redeemed."
    mine = customer_redemptions(coupon, customer, exclude_order=exclude_order)
    if mine is not None and mine.count() >= coupon.max_uses_per_customer:
        return COUPON_CUSTOMER_CAP, "You have already used this coupon."
    return "", ""


def coupon_discount(coupon, subtotal_paise):
    """Discount in paise for a valid coupon. Never more than the subtotal."""
    from store.models import COUPON_KIND_FLAT

    if subtotal_paise <= 0:
        return 0
    if coupon.kind == COUPON_KIND_FLAT:
        return min(int(coupon.flat_off_paise), subtotal_paise)
    percent = max(0, min(int(coupon.discount), 100))
    return subtotal_paise * percent // 100


def _normalise_lines(lines):
    """Accept (variant, qty) or (variant, qty, unit_price_paise) and validate each."""
    normalised = []
    for raw in lines or ():
        if len(raw) == 2:
            variant, qty = raw
            unit_price = None
        elif len(raw) == 3:
            variant, qty, unit_price = raw
        else:
            raise PricingError("Each line must be (variant, qty) or (variant, qty, unit_price_paise).")
        if variant is None:
            raise PricingError("A line has no variant.")
        if unit_price is None:
            unit_price = int(variant.price_paise)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise PricingError(f"Quantity must be a whole number of at least 1, got {qty!r}.")
        if isinstance(unit_price, bool) or not isinstance(unit_price, int) or unit_price < 0:
            raise PricingError(f"Unit price must be a non-negative integer number of paise, got {unit_price!r}.")
        normalised.append((variant, qty, unit_price))
    return normalised


# --------------------------------------------------------------------------- the function

def quote(lines, coupon_code=None, customer=None, exclude_order=None, lock_coupon=False, config=None, now=None):
    """
    Price a set of lines.

    lines         iterable of (variant, qty) or (variant, qty, unit_price_paise)
    coupon_code   optional coupon code typed by the customer
    customer      store.pricing.Customer (or None while the buyer is still anonymous)
    exclude_order an order whose own redemption must not count against the caps
                  (used when an existing order is re-quoted)
    lock_coupon   lock the coupon row (SELECT ... FOR UPDATE); the caller must then be inside
                  transaction.atomic() and write the redemption in that same transaction
    """
    config = config or get_pricing_config()
    items = _normalise_lines(lines)

    line_subtotals = [unit_price * qty for _variant, qty, unit_price in items]
    subtotal = sum(line_subtotals)

    coupon = None
    code = str(coupon_code or "").strip()
    error = message = ""
    discount = 0
    if code and items:
        coupon = find_coupon(code, lock=lock_coupon)
        error, message = check_coupon(coupon, subtotal, customer=customer, exclude_order=exclude_order, now=now)
        if error:
            coupon = None
        else:
            discount = coupon_discount(coupon, subtotal)

    discounts = split_discount(discount, line_subtotals)

    if not items:
        shipping = 0
    elif subtotal - discount >= config.free_shipping_threshold_paise:
        shipping = 0
    else:
        shipping = config.shipping_flat_paise

    total = subtotal - discount + shipping
    tax = carve_out_tax(total, config.tax_rate_bps)

    quote_lines = []
    for (variant, qty, unit_price), line_subtotal, line_discount in zip(items, line_subtotals, discounts):
        line_total = line_subtotal - line_discount
        quote_lines.append(
            QuoteLine(
                variant=variant,
                qty=qty,
                unit_price_paise=unit_price,
                line_subtotal_paise=line_subtotal,
                discount_paise=line_discount,
                line_total_paise=line_total,
                tax_paise=carve_out_tax(line_total, config.tax_rate_bps),
            )
        )

    if not items or shipping == 0:
        to_free = 0
    else:
        to_free = max(config.free_shipping_threshold_paise - (subtotal - discount), 0)

    return Quote(
        lines=quote_lines,
        subtotal_paise=subtotal,
        discount_paise=discount,
        shipping_paise=shipping,
        tax_paise=tax,
        total_paise=total,
        coupon=coupon,
        coupon_code=coupon.code if coupon is not None else "",
        coupon_error=error,
        coupon_message=message,
        shipping_flat_paise=config.shipping_flat_paise,
        free_shipping_threshold_paise=config.free_shipping_threshold_paise,
        amount_to_free_shipping_paise=to_free,
        tax_rate_bps=config.tax_rate_bps,
    )


# --------------------------------------------------------------------------- persistence

def apply_quote_to_order(order, order_items, priced):
    """
    Store a quote on an order as its snapshot. `order_items` must be in the same sequence as
    `priced.lines`. Both paise columns and their Decimal mirrors are written (A5). Saves.
    """
    from store.money_mirror import set_money

    if len(order_items) != len(priced.lines):
        raise PricingError("Order items and quote lines do not line up.")

    for item, line in zip(order_items, priced.lines):
        item.qty = line.qty
        set_money(item, "price", line.unit_price_paise)
        set_money(item, "sub_total", line.line_subtotal_paise)
        set_money(item, "saved", line.discount_paise)
        set_money(item, "shipping_amount", 0)
        set_money(item, "service_fee", 0)
        set_money(item, "tax_fee", line.tax_paise)
        set_money(item, "initial_total", line.line_subtotal_paise)
        set_money(item, "total", line.line_total_paise)
        item.applied_coupon = line.discount_paise > 0
        item.save()

    set_money(order, "sub_total", priced.subtotal_paise)
    set_money(order, "saved", priced.discount_paise)
    set_money(order, "shipping_amount", priced.shipping_paise)
    set_money(order, "service_fee", 0)
    set_money(order, "tax_fee", priced.tax_paise)
    set_money(order, "initial_total", priced.subtotal_paise + priced.shipping_paise)
    set_money(order, "total", priced.total_paise)
    order.coupon_code = priced.coupon_code
    order.save()
    return order


def record_redemption(order, priced, customer):
    """
    Write the append-only redemption row for the coupon on `priced`, once per (coupon, order).
    Must run inside the transaction that locked the coupon (quote(..., lock_coupon=True)).
    """
    from store.models import CouponRedemption

    if priced.coupon is None:
        return None
    existing = CouponRedemption.objects.filter(coupon=priced.coupon, order=order).first()
    if existing is not None:
        return existing
    return CouponRedemption.objects.create(
        coupon=priced.coupon,
        order=order,
        user=customer.user if customer is not None else None,
        email=customer.email if customer is not None else "",
        phone_e164=customer.phone_e164 if customer is not None else "",
        discount_paise=priced.discount_paise,
    )
