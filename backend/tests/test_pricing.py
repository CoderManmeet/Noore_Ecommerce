"""
Phase G1 tests: pricing in INR and integer paise.

Covers the single pricing function `store.pricing.quote()`, shipping thresholds, coupons
(percent and flat, every refusal reason, redemption bookkeeping), the tax carve-out, the
paise/Decimal mirror, order snapshots, the owner-dashboard price edit, the Stripe currency
switch, stock securing on payment and the stale-draft expiry job.

Every test here fails before Phase G1 (store.pricing, store.money_mirror and the paise
columns did not exist) and passes after it.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from catalog.models import ProductVariant
from core.models import AppendOnlyError
from core.money import to_paise
from inventory.models import Batch, ReservationStatus, StockReservation
from inventory.services import available_qty, expire_due_reservations, receive_production
from store.jobs import expire_stale_order_drafts
from store.models import Cart, CartOrder, CartOrderItem, Coupon, CouponRedemption, Product
from store.money_mirror import MoneyMirrorError, assert_mirrors, mirror_mismatches
from store.order_state import cancel_order, mark_paid
from store.pricing import (
    COUPON_CUSTOMER_CAP,
    COUPON_EXPIRED,
    COUPON_NOT_FOUND,
    COUPON_NOT_STARTED,
    COUPON_TOTAL_CAP,
    COUPON_UNDER_MINIMUM,
    Customer,
    PricingError,
    carve_out_tax,
    live_redemptions,
    quote,
    split_discount,
)

API = "/api/v1/"

ADDRESS = {
    "full_name": "Asha Rao", "email": "asha@example.com", "mobile": "9876543210",
    "address": "12 MG Road", "city": "Ludhiana", "state": "Punjab", "country": "India", "pincode": "141001",
}


# --------------------------------------------------------------------------- helpers

def make_candle(vendor, title, price_paise, stock=50, mrp_paise=None):
    """A published product whose default variant sells at `price_paise`, with stock."""
    product = Product.objects.create(title=title, price=Decimal(price_paise) / 100, stock_qty=0,
                                     status="published", vendor=vendor)
    variant = ProductVariant.objects.get(product=product, is_default=True)
    if mrp_paise is not None:
        variant.mrp_paise = mrp_paise
        variant.save()
    if stock:
        add_stock(variant, stock)
    return variant


def add_stock(variant, qty):
    batch = Batch.objects.create(batch_code=f"T-{variant.sku}-{Batch.objects.count()}", variant=variant,
                                 manufactured_on=timezone.localdate(), best_before=None,
                                 quantity_produced=qty, cost_per_unit_paise=0)
    receive_production(variant, batch, qty)
    return batch


def add_to_cart(client, variant, qty, cart_id):
    response = client.post(f"{API}cart-view/", {"product": variant.product_id, "variant": variant.id, "qty": qty,
                                                "user": "undefined", "country": "India", "cart_id": cart_id})
    assert response.status_code in (200, 201), response.content
    return response


def create_order(client, cart_id, **overrides):
    payload = {**ADDRESS, "cart_id": cart_id, **overrides}
    return client.post(f"{API}create-order/", payload)


def assert_order_mirrors(order):
    """The shared A5 assertion: every money pair on the order and on each of its lines."""
    order.refresh_from_db()
    assert_mirrors(order)
    for item in CartOrderItem.objects.filter(order=order):
        assert_mirrors(item)


def assert_order_equals_quote(order, priced):
    order.refresh_from_db()
    assert order.sub_total_paise == priced.subtotal_paise
    assert order.saved_paise == priced.discount_paise
    assert order.shipping_amount_paise == priced.shipping_paise
    assert order.tax_fee_paise == priced.tax_paise
    assert order.total_paise == priced.total_paise
    assert order.service_fee_paise == 0
    items = list(CartOrderItem.objects.filter(order=order).order_by("id"))
    assert len(items) == len(priced.lines)
    for item, line in zip(items, priced.lines):
        assert item.variant_id == line.variant.pk
        assert item.qty == line.qty
        assert item.price_paise == line.unit_price_paise
        assert item.sub_total_paise == line.line_subtotal_paise
        assert item.saved_paise == line.discount_paise
        assert item.total_paise == line.line_total_paise


@pytest.fixture
def candle_920(vendor, config_settings):
    return make_candle(vendor, "Candle 920", 92000)


@pytest.fixture
def candle_999(vendor, config_settings):
    return make_candle(vendor, "Candle 999", 99900)


@pytest.fixture
def candle_1100(vendor, config_settings):
    return make_candle(vendor, "Candle 1100", 110000)


@pytest.fixture
def save10(vendor):
    return Coupon.objects.create(vendor=vendor, code="SAVE10", discount=10, active=True, max_uses_per_customer=1)


# --------------------------------------------------------------------------- shipping

@pytest.mark.django_db
def test_cart_of_920_pays_79_shipping(candle_920):
    priced = quote([(candle_920, 1)])
    assert (priced.subtotal_paise, priced.shipping_paise, priced.total_paise) == (92000, 7900, 99900)
    assert priced.amount_to_free_shipping_paise == 7900


@pytest.mark.django_db
def test_cart_of_exactly_999_ships_free(candle_999):
    priced = quote([(candle_999, 1)])
    assert (priced.subtotal_paise, priced.shipping_paise, priced.total_paise) == (99900, 0, 99900)
    assert priced.free_shipping is True
    assert priced.amount_to_free_shipping_paise == 0


@pytest.mark.django_db
def test_cart_of_1100_with_ten_percent_off_drops_below_the_threshold_and_pays_shipping(candle_1100, save10):
    priced = quote([(candle_1100, 1)], coupon_code="save10")
    assert priced.subtotal_paise == 110000
    assert priced.discount_paise == 11000
    assert priced.shipping_paise == 7900  # Rs 990 after discount is under Rs 999
    assert priced.total_paise == 110000 - 11000 + 7900
    assert priced.amount_to_free_shipping_paise == 900


@pytest.mark.django_db
def test_an_empty_cart_has_no_shipping_and_no_total(config_settings):
    priced = quote([])
    assert (priced.subtotal_paise, priced.shipping_paise, priced.total_paise) == (0, 0, 0)
    assert priced.free_shipping is False


@pytest.mark.django_db
def test_shipping_settings_come_from_config(candle_920, config_settings):
    config_settings.shipping_flat_paise = 4900
    config_settings.free_shipping_threshold_paise = 50000
    config_settings.save()
    assert quote([(candle_920, 1)]).shipping_paise == 0
    config_settings.free_shipping_threshold_paise = 200000
    config_settings.save()
    assert quote([(candle_920, 1)]).shipping_paise == 4900


@pytest.mark.django_db
def test_quote_rejects_bad_lines(candle_920):
    for bad in ([(candle_920, 0)], [(candle_920, -1)], [(candle_920, 1.5)], [(None, 1)], [(candle_920, 1, -5)]):
        with pytest.raises(PricingError):
            quote(bad)


# --------------------------------------------------------------------------- discounts

def test_split_discount_uses_largest_remainder_and_always_sums():
    assert split_discount(100, [1, 1, 1]) == [34, 33, 33]
    assert split_discount(1, [50000, 50000]) == [1, 0]
    assert split_discount(0, [100, 200]) == [0, 0]
    for discount, subtotals in ((3333, [49900, 79900, 119900]), (7, [1, 2, 3, 4]), (99999, [100000])):
        shares = split_discount(discount, subtotals)
        assert sum(shares) == discount
        assert all(0 <= share <= subtotal for share, subtotal in zip(shares, subtotals))


@pytest.mark.django_db
def test_percentage_coupon_discounts_every_line_and_lines_sum_to_the_order(vendor, config_settings):
    a = make_candle(vendor, "A", 49900)
    b = make_candle(vendor, "B", 79900)
    c = make_candle(vendor, "C", 33333)
    Coupon.objects.create(vendor=vendor, code="THIRD", discount=33, active=True)

    priced = quote([(a, 1), (b, 2), (c, 3)], coupon_code="THIRD")

    subtotal = 49900 + 2 * 79900 + 3 * 33333
    assert priced.subtotal_paise == subtotal
    assert priced.discount_paise == subtotal * 33 // 100  # rounds down to a whole paisa
    assert all(line.discount_paise > 0 for line in priced.lines)  # every line, not just the first
    assert sum(line.discount_paise for line in priced.lines) == priced.discount_paise
    assert sum(line.line_total_paise for line in priced.lines) == priced.subtotal_paise - priced.discount_paise
    assert priced.total_paise == sum(line.line_total_paise for line in priced.lines) + priced.shipping_paise


@pytest.mark.django_db
def test_flat_coupon_larger_than_the_subtotal_takes_the_subtotal_to_zero_never_below(candle_920, vendor):
    Coupon.objects.create(vendor=vendor, code="BIGFLAT", kind="FLAT", flat_off_paise=500000, active=True)
    priced = quote([(candle_920, 1)], coupon_code="BIGFLAT")
    assert priced.discount_paise == 92000
    assert priced.lines[0].line_total_paise == 0
    assert priced.shipping_paise == 7900  # Rs 0 after discount is under the free-shipping threshold
    assert priced.total_paise == 7900


@pytest.mark.django_db
def test_flat_coupon_takes_a_fixed_amount_off(candle_1100, vendor):
    Coupon.objects.create(vendor=vendor, code="FLAT100", kind="FLAT", flat_off_paise=10000, active=True)
    priced = quote([(candle_1100, 1)], coupon_code="FLAT100")
    assert priced.discount_paise == 10000
    assert priced.shipping_paise == 0  # Rs 1,000 after discount still ships free
    assert priced.total_paise == 100000


@pytest.mark.django_db
def test_free_shipping_and_a_coupon_combine(candle_1100, vendor):
    Coupon.objects.create(vendor=vendor, code="FIVE", discount=5, active=True)
    priced = quote([(candle_1100, 1)], coupon_code="FIVE")
    assert priced.discount_paise == 5500
    assert priced.shipping_paise == 0
    assert priced.total_paise == 104500


# --------------------------------------------------------------------------- coupon refusals

@pytest.mark.django_db
def test_unknown_or_inactive_coupon_is_refused_without_a_discount(candle_920, vendor):
    Coupon.objects.create(vendor=vendor, code="OFF", discount=10, active=False)
    for code in ("NOPE", "OFF"):
        priced = quote([(candle_920, 1)], coupon_code=code)
        assert priced.coupon_error == COUPON_NOT_FOUND
        assert priced.coupon_message
        assert priced.discount_paise == 0
        assert priced.total_paise == 99900


@pytest.mark.django_db
def test_coupon_is_refused_outside_its_date_window(candle_920, vendor):
    now = timezone.now()
    Coupon.objects.create(vendor=vendor, code="OLD", discount=10, active=True, valid_until=now - timedelta(minutes=1))
    Coupon.objects.create(vendor=vendor, code="SOON", discount=10, active=True, valid_from=now + timedelta(days=1))
    Coupon.objects.create(vendor=vendor, code="NOW", discount=10, active=True,
                          valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1))

    expired = quote([(candle_920, 1)], coupon_code="OLD")
    early = quote([(candle_920, 1)], coupon_code="SOON")
    live = quote([(candle_920, 1)], coupon_code="NOW")

    assert (expired.coupon_error, expired.discount_paise) == (COUPON_EXPIRED, 0)
    assert (early.coupon_error, early.discount_paise) == (COUPON_NOT_STARTED, 0)
    assert (live.coupon_error, live.discount_paise) == ("", 9200)


@pytest.mark.django_db
def test_coupon_is_refused_under_its_minimum_order(candle_920, candle_1100, vendor):
    Coupon.objects.create(vendor=vendor, code="MIN1000", discount=10, active=True, min_order_paise=100000)
    under = quote([(candle_920, 1)], coupon_code="MIN1000")
    over = quote([(candle_1100, 1)], coupon_code="MIN1000")
    assert (under.coupon_error, under.discount_paise) == (COUPON_UNDER_MINIMUM, 0)
    assert "1,000" in under.coupon_message
    assert (over.coupon_error, over.discount_paise) == ("", 11000)


@pytest.mark.django_db
def test_coupon_is_refused_over_its_total_cap(api, candle_920, vendor):
    Coupon.objects.create(vendor=vendor, code="FIRST1", discount=10, active=True, max_total_uses=1,
                          max_uses_per_customer=5)
    add_to_cart(api, candle_920, 1, "cap-cart-1")
    first = create_order(api, "cap-cart-1", coupon_code="FIRST1")
    assert first.json()["coupon_error"] == ""

    add_to_cart(api, candle_920, 1, "cap-cart-2")
    second = create_order(api, "cap-cart-2", coupon_code="FIRST1", email="someone.else@example.com",
                          mobile="9123456780")
    assert second.status_code == 201
    assert second.json()["coupon_error"] == COUPON_TOTAL_CAP
    order = CartOrder.objects.get(oid=second.json()["order_oid"])
    assert order.saved_paise == 0
    assert order.total_paise == 99900
    assert CouponRedemption.objects.count() == 1


@pytest.mark.django_db
def test_coupon_is_refused_over_the_per_customer_cap_for_a_signed_in_customer(auth, customer, other_customer,
                                                                               candle_920, save10):
    client = auth(customer)
    add_to_cart(client, candle_920, 1, "pc-cart-1")
    assert create_order(client, "pc-cart-1", coupon_code="SAVE10", user_id=customer.id).json()["coupon_error"] == ""

    add_to_cart(client, candle_920, 1, "pc-cart-2")
    again = create_order(client, "pc-cart-2", coupon_code="SAVE10", user_id=customer.id,
                         email="different@example.com", mobile="9000000001")
    assert again.json()["coupon_error"] == COUPON_CUSTOMER_CAP
    assert CartOrder.objects.get(oid=again.json()["order_oid"]).saved_paise == 0

    # The cart preview already knows who is signed in, so it warns before checkout.
    preview = client.get(f"{API}cart-detail/pc-cart-2/{customer.id}/?coupon=SAVE10").json()
    assert preview["coupon_error"] == COUPON_CUSTOMER_CAP

    # Somebody else may still use it.
    other = auth(other_customer)
    add_to_cart(other, candle_920, 1, "pc-cart-3")
    assert create_order(other, "pc-cart-3", coupon_code="SAVE10", user_id=other_customer.id).json()["coupon_error"] == ""


@pytest.mark.django_db
def test_coupon_is_refused_over_the_per_customer_cap_for_a_guest_by_email_or_phone(api, candle_920, save10):
    add_to_cart(api, candle_920, 1, "g-cart-1")
    assert create_order(api, "g-cart-1", coupon_code="SAVE10").json()["coupon_error"] == ""

    # Same email (different case and spacing), different phone.
    add_to_cart(api, candle_920, 1, "g-cart-2")
    same_email = create_order(api, "g-cart-2", coupon_code="SAVE10", email="  ASHA@Example.com ", mobile="9000000002")
    assert same_email.json()["coupon_error"] == COUPON_CUSTOMER_CAP

    # Same phone (written differently), different email.
    add_to_cart(api, candle_920, 1, "g-cart-3")
    same_phone = create_order(api, "g-cart-3", coupon_code="SAVE10", email="new@example.com", mobile="+91 98765 43210")
    assert same_phone.json()["coupon_error"] == COUPON_CUSTOMER_CAP

    # Known limitation, accepted in the roadmap: a guest with a new email AND a new phone
    # is a new customer as far as the cap can tell.
    add_to_cart(api, candle_920, 1, "g-cart-4")
    evader = create_order(api, "g-cart-4", coupon_code="SAVE10", email="fresh@example.com", mobile="9000000003")
    assert evader.json()["coupon_error"] == ""


@pytest.mark.django_db
def test_each_refusal_has_its_own_message(candle_920, vendor, customer):
    now = timezone.now()
    Coupon.objects.create(vendor=vendor, code="A-EXPIRED", discount=10, active=True, valid_until=now - timedelta(days=1))
    Coupon.objects.create(vendor=vendor, code="A-EARLY", discount=10, active=True, valid_from=now + timedelta(days=1))
    Coupon.objects.create(vendor=vendor, code="A-MIN", discount=10, active=True, min_order_paise=10000000)
    capped = Coupon.objects.create(vendor=vendor, code="A-CAP", discount=10, active=True, max_total_uses=0)
    personal = Coupon.objects.create(vendor=vendor, code="A-MINE", discount=10, active=True, max_uses_per_customer=0)
    assert capped.pk and personal.pk

    messages = {}
    for code in ("A-NONE", "A-EXPIRED", "A-EARLY", "A-MIN", "A-CAP", "A-MINE"):
        priced = quote([(candle_920, 1)], coupon_code=code, customer=Customer.build(user=customer))
        assert priced.coupon_error and priced.discount_paise == 0
        messages[priced.coupon_error] = priced.coupon_message
    assert set(messages) == {COUPON_NOT_FOUND, COUPON_EXPIRED, COUPON_NOT_STARTED, COUPON_UNDER_MINIMUM,
                             COUPON_TOTAL_CAP, COUPON_CUSTOMER_CAP}
    assert len(set(messages.values())) == 6


# --------------------------------------------------------------------------- redemptions

@pytest.mark.django_db
def test_redemption_is_recorded_once_and_is_append_only(api, candle_920, save10):
    add_to_cart(api, candle_920, 1, "r-cart-1")
    create_order(api, "r-cart-1", coupon_code="SAVE10")
    create_order(api, "r-cart-1", coupon_code="SAVE10")  # re-posting the same checkout

    redemption = CouponRedemption.objects.get()
    assert redemption.coupon == save10
    assert redemption.discount_paise == 9200
    assert redemption.email == "asha@example.com"
    assert redemption.phone_e164 == "+919876543210"
    assert redemption.user is None

    redemption.discount_paise = 1
    with pytest.raises(AppendOnlyError):
        redemption.save()
    with pytest.raises(AppendOnlyError):
        redemption.delete()
    with pytest.raises(AppendOnlyError):
        CouponRedemption.objects.all().delete()


@pytest.mark.django_db
def test_cancelling_an_order_frees_its_redemption(api, candle_920, save10):
    add_to_cart(api, candle_920, 1, "c-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "c-cart-1", coupon_code="SAVE10").json()["order_oid"])
    assert live_redemptions(save10).count() == 1

    add_to_cart(api, candle_920, 1, "c-cart-2")
    assert create_order(api, "c-cart-2", coupon_code="SAVE10").json()["coupon_error"] == COUPON_CUSTOMER_CAP

    cancel_order(order, reason="customer changed their mind")
    assert_order_mirrors(order)
    assert live_redemptions(save10).count() == 0

    retry = create_order(api, "c-cart-2", coupon_code="SAVE10")
    assert retry.json()["coupon_error"] == ""
    assert CartOrder.objects.get(oid=retry.json()["order_oid"]).saved_paise == 9200


@pytest.mark.django_db
def test_removing_or_replacing_a_coupon_on_the_order_frees_it(api, candle_920, save10, vendor):
    other = Coupon.objects.create(vendor=vendor, code="OTHER5", discount=5, active=True)
    add_to_cart(api, candle_920, 1, "sw-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "sw-cart-1", coupon_code="SAVE10").json()["order_oid"])

    swap = api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": "other5"})
    assert swap.status_code == 200
    order.refresh_from_db()
    assert (order.coupon_code, order.saved_paise) == ("OTHER5", 4600)
    assert live_redemptions(save10).count() == 0
    assert live_redemptions(other).count() == 1

    removed = api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": ""})
    assert removed.status_code == 200
    assert removed.json()["message"] == "Coupon Removed"
    order.refresh_from_db()
    assert (order.coupon_code, order.saved_paise, order.total_paise) == ("", 0, 99900)
    assert live_redemptions(other).count() == 0
    assert_order_mirrors(order)


@pytest.mark.django_db
def test_coupon_endpoint_refuses_with_the_reason_and_leaves_the_order_alone(api, candle_920, vendor):
    Coupon.objects.create(vendor=vendor, code="OLD", discount=10, active=True,
                          valid_until=timezone.now() - timedelta(days=1))
    add_to_cart(api, candle_920, 1, "ce-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "ce-cart-1").json()["order_oid"])

    response = api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": "OLD"})
    assert response.status_code == 400
    assert response.json()["coupon_error"] == COUPON_EXPIRED
    assert response.json()["message"] == "This coupon has expired."
    order.refresh_from_db()
    assert (order.saved_paise, order.total_paise) == (0, 99900)
    assert CouponRedemption.objects.count() == 0


# --------------------------------------------------------------------------- order = quote

@pytest.mark.django_db
def test_a_tampered_client_total_is_ignored_and_the_stored_order_equals_the_quote(api, vendor, config_settings, save10):
    a = make_candle(vendor, "A", 49900)
    b = make_candle(vendor, "B", 79900)
    add_to_cart(api, a, 2, "t-cart-1")
    add_to_cart(api, b, 1, "t-cart-1")

    response = create_order(api, "t-cart-1", coupon_code="SAVE10", total="1.00", total_paise=1, sub_total="1.00",
                            shipping_amount="0", shipping_paise=0, saved="9999", discount_paise=999999,
                            service_fee="0", tax_fee="0", price="1")
    assert response.status_code == 201

    order = CartOrder.objects.get(oid=response.json()["order_oid"])
    expected = quote([(a, 2), (b, 1)], coupon_code="SAVE10", exclude_order=order)
    assert expected.total_paise == (2 * 49900 + 79900) * 90 // 100  # Rs 1,617.30, ships free
    assert_order_equals_quote(order, expected)
    assert response.json()["total_paise"] == expected.total_paise
    assert order.coupon_code == "SAVE10"
    assert_order_mirrors(order)


@pytest.mark.django_db
def test_no_order_carries_a_service_fee_or_added_tax(api, candle_920, config_settings):
    from addon.models import Tax

    config_settings.service_fee_percentage = 5
    config_settings.service_fee_charge_type = "percentage"
    config_settings.save()
    Tax.objects.create(country="India", rate=18, active=True)

    add_to_cart(api, candle_920, 3, "sf-cart-1")
    line = Cart.objects.get(cart_id="sf-cart-1")
    assert (line.service_fee_paise, line.tax_fee_paise, line.shipping_amount_paise) == (0, 0, 0)

    totals = api.get(f"{API}cart-detail/sf-cart-1/").json()
    assert "service_fee" not in totals and "tax" not in totals
    assert totals["total_paise"] == 3 * 92000  # ships free, nothing added on top

    order = CartOrder.objects.get(oid=create_order(api, "sf-cart-1").json()["order_oid"])
    assert (order.service_fee_paise, order.tax_fee_paise) == (0, 0)
    assert order.total_paise == 276000
    assert all(item.service_fee_paise == 0 and item.tax_fee_paise == 0 for item in order.orderitem.all())


@pytest.mark.django_db
def test_tax_is_carved_out_of_the_price_and_never_changes_the_total(candle_920, config_settings):
    untaxed = quote([(candle_920, 1)])
    config_settings.tax_rate_bps = 1800
    config_settings.save()
    taxed = quote([(candle_920, 1)])

    assert untaxed.tax_paise == 0
    assert taxed.total_paise == untaxed.total_paise == 99900
    assert taxed.tax_paise == carve_out_tax(99900, 1800) == 15239  # 99900 x 18 / 118, half-up
    assert taxed.lines[0].tax_paise == carve_out_tax(92000, 1800)
    assert carve_out_tax(11800, 1800) == 1800
    assert carve_out_tax(0, 1800) == 0


@pytest.mark.django_db
def test_a_later_price_change_never_alters_an_existing_order(api, candle_920, save10):
    add_to_cart(api, candle_920, 1, "snap-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "snap-cart-1").json()["order_oid"])
    assert order.total_paise == 99900

    candle_920.price_paise = 150000
    candle_920.save()

    order.refresh_from_db()
    assert order.total_paise == 99900
    assert order.orderitem.get().price_paise == 92000

    # Applying a coupon afterwards re-prices from the order's own snapshot, not today's price.
    assert api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": "SAVE10"}).status_code == 200
    order.refresh_from_db()
    assert (order.sub_total_paise, order.saved_paise, order.total_paise) == (92000, 9200, 82800 + 7900)

    # A new cart, on the other hand, sees the new price.
    add_to_cart(api, candle_920, 1, "snap-cart-2")
    assert api.get(f"{API}cart-detail/snap-cart-2/").json()["subtotal_paise"] == 150000


@pytest.mark.django_db
def test_two_variants_of_one_product_are_two_cart_lines(api, vendor, config_settings):
    small = make_candle(vendor, "Scent", 49900)
    large = ProductVariant.objects.create(product=small.product, sku="SCENT-300", name="300 g", price_paise=119900)
    add_stock(large, 5)

    add_to_cart(api, small, 1, "v-cart-1")
    add_to_cart(api, large, 2, "v-cart-1")

    assert Cart.objects.filter(cart_id="v-cart-1").count() == 2
    totals = api.get(f"{API}cart-detail/v-cart-1/").json()
    assert totals["subtotal_paise"] == 49900 + 2 * 119900
    assert {line["variant_id"] for line in totals["lines"]} == {small.id, large.id}
    assert all("cart_item_id" in line for line in totals["lines"])

    bogus = api.post(f"{API}cart-view/", {"product": small.product_id, "variant": 999999, "qty": 1,
                                         "user": "undefined", "cart_id": "v-cart-1"})
    assert bogus.status_code == 400


# --------------------------------------------------------------------------- mirror (A5)

@pytest.mark.django_db
def test_mirrors_hold_after_every_order_write(api, vendor, config_settings, save10):
    """create -> quantity change -> coupon applied -> payment -> cancel, checking after each."""
    a = make_candle(vendor, "A", 49950)
    b = make_candle(vendor, "B", 33333)

    add_to_cart(api, a, 1, "m-cart-1")
    add_to_cart(api, b, 3, "m-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "m-cart-1").json()["order_oid"])
    assert_order_mirrors(order)
    assert order.total == Decimal("1499.49") and order.total_paise == 149949  # over Rs 999: ships free

    add_to_cart(api, a, 4, "m-cart-1")  # quantity change, then back through checkout
    assert create_order(api, "m-cart-1").status_code == 200
    assert_order_mirrors(order)
    assert order.orderitem.get(variant=a).qty == 4
    assert order.sub_total_paise == 4 * 49950 + 3 * 33333

    assert api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": "SAVE10"}).status_code == 200
    assert_order_mirrors(order)
    assert order.saved == Decimal("299.79") and order.saved_paise == 29979

    mark_paid(order, reason="test payment")
    assert_order_mirrors(order)

    cancel_order(order, reason="test cancel")
    assert_order_mirrors(order)
    assert order.order_status == "Cancelled"


@pytest.mark.django_db
def test_the_mirror_assertion_catches_a_paise_value_written_without_its_mirror(api, candle_920):
    add_to_cart(api, candle_920, 1, "d-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "d-cart-1").json()["order_oid"])
    assert_mirrors(order)

    # queryset.update() bypasses save(), which is the only way to make a pair drift.
    CartOrder.objects.filter(pk=order.pk).update(total_paise=12345)
    order.refresh_from_db()
    assert mirror_mismatches(order) == [("total", Decimal("999.00"), 12345)]
    with pytest.raises(MoneyMirrorError):
        assert_mirrors(order)

    item = order.orderitem.get()
    CartOrderItem.objects.filter(pk=item.pk).update(sub_total_paise=1)
    item.refresh_from_db()
    with pytest.raises(MoneyMirrorError):
        assert_mirrors(item)


@pytest.mark.django_db
def test_save_keeps_both_sides_in_step_whichever_side_was_written(make_order):
    legacy = make_order(total=Decimal("59.00"))  # legacy code writes Decimal only
    assert legacy.total_paise == 5900 and legacy.sub_total_paise == 5900

    legacy.total_paise = 7000  # new code writes paise only
    legacy.save()
    legacy.refresh_from_db()
    assert legacy.total == Decimal("70.00")

    legacy.total = Decimal("12.34")  # e.g. an edit in Django admin
    legacy.save(update_fields=["total"])
    legacy.refresh_from_db()
    assert legacy.total_paise == 1234
    assert to_paise(legacy.total) == legacy.total_paise


# --------------------------------------------------------------------------- catalogue price

@pytest.mark.django_db
def test_owner_dashboard_price_edit_writes_the_default_variant(auth, staff, vendor, product):
    variant = ProductVariant.objects.get(product=product, is_default=True)
    assert variant.price_paise == 5600

    response = auth(staff).patch(f"{API}vendor-product-edit/{vendor.id}/{product.pid}/",
                                 {"price": "64.50", "old_price": "80.00"}, format="multipart")
    assert response.status_code == 200

    variant.refresh_from_db()
    product.refresh_from_db()
    assert (variant.price_paise, variant.mrp_paise) == (6450, 8000)
    assert product.price == Decimal("64.50")  # the legacy column is the mirror


@pytest.mark.django_db
def test_changing_the_default_variant_price_mirrors_back_to_the_product(product):
    variant = ProductVariant.objects.get(product=product, is_default=True)
    variant.price_paise = 4999
    variant.mrp_paise = None
    variant.save()
    product.refresh_from_db()
    assert (product.price, product.old_price) == (Decimal("49.99"), Decimal("0.00"))

    # Saving the product for an unrelated reason must not push a stale price back.
    stale = Product.objects.get(pk=product.pk)
    variant.price_paise = 5100
    variant.save()
    stale.title = "Renamed"
    stale.save()
    variant.refresh_from_db()
    assert variant.price_paise == 5100
    assert Product.objects.get(pk=product.pk).price == Decimal("51.00")  # and the mirror is repaired


@pytest.mark.django_db
def test_a_new_product_gets_a_default_variant_and_its_opening_stock(vendor, config_settings):
    product = Product.objects.create(title="Fresh", price=Decimal("499.00"), old_price=Decimal("599.00"),
                                     stock_qty=7, status="published", vendor=vendor)
    variant = ProductVariant.objects.get(product=product)
    assert (variant.is_default, variant.active, variant.price_paise, variant.mrp_paise) == (True, True, 49900, 59900)
    assert available_qty(variant) == 7

    product.save()  # saving again creates nothing new
    assert ProductVariant.objects.filter(product=product).count() == 1
    assert available_qty(variant) == 7


@pytest.mark.django_db
def test_currency_is_inr(config_settings, api):
    assert config_settings.currency_sign == "\u20b9"
    assert config_settings.currency_abbreviation == "INR"
    body = api.get(f"{API}addon/").json()
    assert body["currency_sign"] == "\u20b9"
    assert (body["shipping_flat_paise"], body["free_shipping_threshold_paise"], body["tax_rate_bps"]) == (7900, 99900, 0)


# --------------------------------------------------------------------------- payment

@pytest.mark.django_db
def test_stripe_session_is_created_in_inr_for_the_stored_paise_total(api, candle_920, save10, settings, legacy_providers):
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"
    add_to_cart(api, candle_920, 1, "s-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "s-cart-1", coupon_code="SAVE10").json()["order_oid"])

    session = mock.Mock(id="cs_test_g1", url="https://checkout.stripe.test/pay/cs_test_g1")
    with mock.patch("store.views.stripe.checkout.Session.create", return_value=session) as create:
        response = api.post(f"{API}stripe-checkout/{order.oid}/")

    assert response.status_code == 302
    price_data = create.call_args.kwargs["line_items"][0]["price_data"]
    assert price_data["currency"] == "inr"
    assert price_data["unit_amount"] == order.total_paise == 92000 - 9200 + 7900
    order.refresh_from_db()
    assert order.stripe_session_id == "cs_test_g1"
    assert_order_mirrors(order)


@pytest.mark.django_db
def test_a_paid_orders_stock_survives_the_checkout_hold_expiring(api, candle_920):
    add_to_cart(api, candle_920, 2, "h-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "h-cart-1").json()["order_oid"])
    mark_paid(order, reason="test payment")

    # Long after the 30-minute checkout hold would have lapsed:
    StockReservation.objects.filter(order=order, status=ReservationStatus.ACTIVE).update(
        created_at=timezone.now() - timedelta(days=2))
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=2)):
        assert expire_due_reservations() == 0
        assert available_qty(candle_920) == 48


@pytest.mark.django_db
def test_paying_after_the_hold_lapsed_reserves_the_stock_again(api, candle_920):
    add_to_cart(api, candle_920, 2, "h-cart-2")
    order = CartOrder.objects.get(oid=create_order(api, "h-cart-2").json()["order_oid"])

    StockReservation.objects.filter(order=order).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_due_reservations() == 1
    assert available_qty(candle_920) == 50

    mark_paid(order, reason="paid late")
    assert available_qty(candle_920) == 48
    held = StockReservation.objects.filter(order=order, status=ReservationStatus.ACTIVE)
    assert sum(r.quantity for r in held) == 2
    mark_paid(order, reason="duplicate confirmation")  # idempotent
    assert available_qty(candle_920) == 48


# --------------------------------------------------------------------------- stale drafts

@pytest.mark.django_db
def test_stale_unpaid_drafts_expire_and_give_back_stock_coupon_and_cart(api, candle_920, save10, settings):
    settings.ORDER_DRAFT_TTL_HOURS = 48
    add_to_cart(api, candle_920, 1, "x-cart-1")
    order = CartOrder.objects.get(oid=create_order(api, "x-cart-1", coupon_code="SAVE10").json()["order_oid"])

    assert expire_stale_order_drafts() == 0  # still fresh
    CartOrder.objects.filter(pk=order.pk).update(date=timezone.now() - timedelta(hours=49))
    assert expire_stale_order_drafts() == 1
    assert expire_stale_order_drafts() == 0  # idempotent

    order.refresh_from_db()
    assert order.payment_status == "expired"
    assert available_qty(candle_920) == 50
    assert live_redemptions(save10).count() == 0

    # The same cart can check out again and gets a brand-new order with the coupon.
    add_to_cart(api, candle_920, 1, "x-cart-1")
    again = create_order(api, "x-cart-1", coupon_code="SAVE10")
    assert again.status_code == 201
    assert again.json()["order_oid"] != order.oid
    assert again.json()["coupon_error"] == ""


@pytest.mark.django_db
def test_paid_orders_are_never_expired_by_the_draft_job(api, candle_920):
    add_to_cart(api, candle_920, 1, "x-cart-2")
    order = CartOrder.objects.get(oid=create_order(api, "x-cart-2").json()["order_oid"])
    mark_paid(order, reason="test payment")
    CartOrder.objects.filter(pk=order.pk).update(date=timezone.now() - timedelta(days=30))
    assert expire_stale_order_drafts() == 0
    order.refresh_from_db()
    assert order.payment_status == "paid"


@pytest.mark.django_db
def test_card_payment_is_refused_for_a_draft_too_old_to_outlive_its_session(api, candle_920, settings, legacy_providers):
    settings.STRIPE_SECRET_KEY = "sk_test_dummy"
    settings.ORDER_DRAFT_TTL_HOURS = 48
    add_to_cart(api, candle_920, 1, "x-cart-3")
    order = CartOrder.objects.get(oid=create_order(api, "x-cart-3").json()["order_oid"])
    CartOrder.objects.filter(pk=order.pk).update(date=timezone.now() - timedelta(hours=24))

    with mock.patch("store.views.stripe.checkout.Session.create") as create:
        response = api.post(f"{API}stripe-checkout/{order.oid}/")
    assert response.status_code == 400
    assert not create.called


# --------------------------------------------------------------------------- concurrency

class ConcurrentCouponTest(TransactionTestCase):
    """
    Two simultaneous checkouts, one coupon use left: exactly one gets the discount.

    Needs real row locking, so it is skipped on SQLite (where select_for_update is a no-op)
    rather than passing for the wrong reason.
    """

    reset_sequences = True

    def test_a_capped_coupon_cannot_be_over_used_by_two_simultaneous_checkouts(self):
        if connection.vendor != "postgresql":
            self.skipTest(f"needs PostgreSQL row locking; running on {connection.vendor}")

        import threading

        from addon.models import ConfigSettings
        from store.pricing import record_redemption
        from userauths.models import User
        from vendor.models import Vendor

        ConfigSettings.objects.create()
        owner = User.objects.create_user(email="owner@example.com", username="owner", password="x")
        shop = Vendor.objects.create(user=owner, name="Shop", slug="shop")
        variant = make_candle(shop, "Race Candle", 50000, stock=10)
        Coupon.objects.create(vendor=shop, code="ONLYONE", discount=10, active=True, max_total_uses=1,
                              max_uses_per_customer=5)
        orders = [
            CartOrder.objects.create(full_name=f"Buyer {i}", email=f"buyer{i}@example.com", mobile="9876543210",
                                     payment_status="processing")
            for i in range(2)
        ]

        results = []
        barrier = threading.Barrier(2)

        def attempt(order):
            barrier.wait()
            try:
                customer = Customer.build(email=order.email)
                with transaction.atomic():
                    priced = quote([(variant, 1)], coupon_code="ONLYONE", customer=customer, lock_coupon=True)
                    if priced.coupon is not None:
                        order.coupon_code = priced.coupon_code
                        order.save(update_fields=["coupon_code"])
                        record_redemption(order, priced, customer)
                results.append(priced.coupon_error or "ok")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(order,)) for order in orders]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), sorted(["ok", COUPON_TOTAL_CAP]))
        self.assertEqual(CouponRedemption.objects.count(), 1)
