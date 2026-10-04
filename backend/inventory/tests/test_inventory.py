"""
Phase F-B tests: variants, batches, the stock ledger, FEFO allocation, reservations,
the order state machine and the checkout wiring.

Every test here fails before Phase F-B (the models and services did not exist, and stock
was never decremented) and passes after it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from catalog.models import ProductVariant
from core.phone import InvalidPhoneNumber, mask, to_e164, try_to_e164
from inventory.adapters import ChannelAdapter, get_adapter, register_adapter, registered_channels
from inventory.models import Batch, Channel, MovementKind, ReservationStatus, StockMovement, StockReservation
from inventory.services import (
    InsufficientStock,
    InvalidMovement,
    available_qty,
    batch_on_hand,
    batches_nearing_expiry,
    consume_for_order,
    expire_due_reservations,
    expired_unsold_batches,
    on_hand_qty,
    receive_production,
    reconcile_batch,
    release_for_order,
    reserve,
)
from store.order_state import CODNotConfirmed, OrderStateError, cancel_order, set_delivery_status, set_order_status, set_payment_status

API = "/api/v1/"


def make_batch(variant, code, qty, best_before_days=None, made_days_ago=0, cost_paise=1000):
    today = timezone.localdate()
    batch = Batch.objects.create(
        batch_code=code,
        variant=variant,
        manufactured_on=today - timedelta(days=made_days_ago),
        best_before=(today + timedelta(days=best_before_days)) if best_before_days is not None else None,
        quantity_produced=qty,
        cost_per_unit_paise=cost_paise,
    )
    receive_production(variant, batch, qty)
    return batch


@pytest.fixture
def variant(product):
    """
    The product fixture's default variant, with its opening stock cleared so each test
    starts from an empty ledger and creates exactly the batches it needs.
    """
    variant = ProductVariant.objects.get(product=product, is_default=True)
    # The ledger is append-only in application code; a fixture may reset it with raw SQL
    # so each test below starts from zero and creates exactly the batches it needs.
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM inventory_stockmovement WHERE variant_id = %s", [variant.pk])
        cursor.execute("DELETE FROM inventory_batch WHERE variant_id = %s", [variant.pk])
    return variant


# ------------------------------------------------------------------ variants

@pytest.mark.django_db
def test_a_product_can_only_have_one_default_variant(product, variant):
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        ProductVariant.objects.create(product=product, sku="SKU-TEST-2", price_paise=100, is_default=True)


@pytest.mark.django_db
def test_backfilled_variant_price_matches_the_legacy_decimal_price(product):
    """The backfill converts Decimal rupees to integer paise with no drift."""
    from core.money import from_paise, to_paise

    default = ProductVariant.objects.get(product=product, is_default=True)
    assert default.price_paise == to_paise(product.price) == 5600
    assert from_paise(default.price_paise) == product.price
    assert default.mrp_paise == to_paise(product.old_price)


@pytest.mark.django_db
def test_a_product_may_have_several_non_default_variants(product):
    small = ProductVariant.objects.create(product=product, sku="SKU-S", name="Small", size="S", price_paise=5000)
    large = ProductVariant.objects.create(product=product, sku="SKU-L", name="Large", size="L", price_paise=7000)
    assert product.variants.count() == 3
    assert {small.sku, large.sku}.issubset(set(product.variants.values_list("sku", flat=True)))


# ------------------------------------------------------------------ ledger

@pytest.mark.django_db
def test_available_stock_is_the_sum_of_ledger_movements(variant):
    assert on_hand_qty(variant) == 0
    batch = make_batch(variant, "B1", 100)
    assert on_hand_qty(variant) == 100

    from inventory.services import record_movement

    record_movement(variant, MovementKind.DAMAGE_OUT, -10, batch=batch, reason="crushed in transit")
    record_movement(variant, MovementKind.RETURN_IN, 4, batch=batch, reason="customer return, resellable")

    assert on_hand_qty(variant) == 94
    assert batch_on_hand(batch) == 94
    assert available_qty(variant) == 94
    assert reconcile_batch(batch)["balances"] is True


@pytest.mark.django_db
def test_movements_reject_the_wrong_sign_and_zero(variant):
    batch = make_batch(variant, "B1", 10)
    from inventory.services import record_movement

    with pytest.raises(InvalidMovement):
        record_movement(variant, MovementKind.SALE_OUT, 5, batch=batch)
    with pytest.raises(InvalidMovement):
        record_movement(variant, MovementKind.PRODUCTION_IN, -5, batch=batch)
    with pytest.raises(InvalidMovement):
        record_movement(variant, MovementKind.ADJUSTMENT, 0, batch=batch)


@pytest.mark.django_db
def test_stock_movements_are_append_only(variant):
    from core.models import AppendOnlyError

    make_batch(variant, "B1", 10)
    movement = StockMovement.objects.first()
    movement.quantity = 9999
    with pytest.raises(AppendOnlyError):
        movement.save()
    with pytest.raises(AppendOnlyError):
        StockMovement.objects.all().delete()


@pytest.mark.django_db
def test_every_stock_movement_is_audited(variant, staff):
    from core.audit import acting_as
    from core.models import AuditLog

    with acting_as(staff):
        make_batch(variant, "B1", 25)
    row = AuditLog.objects.filter(action="stock.movement").latest("id")
    assert row.after["quantity"] == 25
    assert row.after["batch"] == "B1"
    assert row.actor_id == staff.id


# ------------------------------------------------------------------ FEFO

@pytest.mark.django_db
def test_allocation_takes_the_soonest_expiry_first(variant):
    late = make_batch(variant, "LATE", 10, best_before_days=365, made_days_ago=30)
    soon = make_batch(variant, "SOON", 10, best_before_days=60, made_days_ago=1)

    reservations = reserve(variant, 6, cart_id="c1")
    assert len(reservations) == 1
    assert reservations[0].batch_id == soon.id
    assert reservations[0].batch_id != late.id


@pytest.mark.django_db
def test_allocation_splits_across_batches_when_one_is_not_enough(variant):
    soon = make_batch(variant, "SOON", 4, best_before_days=60)
    late = make_batch(variant, "LATE", 10, best_before_days=365)

    reservations = reserve(variant, 9, cart_id="c1")
    taken = {r.batch_id: r.quantity for r in reservations}
    assert taken == {soon.id: 4, late.id: 5}
    assert sum(taken.values()) == 9


@pytest.mark.django_db
def test_fifo_strategy_takes_the_oldest_batch_first(variant):
    old = make_batch(variant, "OLD", 10, best_before_days=365, made_days_ago=90)
    make_batch(variant, "NEW", 10, best_before_days=60, made_days_ago=1)

    reservations = reserve(variant, 5, cart_id="c1", strategy="FIFO")
    assert reservations[0].batch_id == old.id


@pytest.mark.django_db
def test_batch_inside_the_minimum_shelf_life_window_is_never_allocated(variant, settings):
    settings.MIN_SHELF_LIFE_ON_DISPATCH_DAYS = 30
    make_batch(variant, "TOO-FRESH-TO-SHIP", 50, best_before_days=10)

    assert on_hand_qty(variant) == 50
    with pytest.raises(InsufficientStock):
        reserve(variant, 1, cart_id="c1")


@pytest.mark.django_db
def test_expired_batch_is_never_allocated_but_still_counts_as_on_hand(variant):
    make_batch(variant, "EXPIRED", 20, best_before_days=-5)
    assert on_hand_qty(variant) == 20
    with pytest.raises(InsufficientStock):
        reserve(variant, 1, cart_id="c1")
    assert [b.batch_code for b, _ in expired_unsold_batches()] == ["EXPIRED"]


@pytest.mark.django_db
def test_batches_nearing_expiry_are_reported(variant, settings):
    settings.EXPIRY_ALERT_DAYS = 45
    make_batch(variant, "SOON", 10, best_before_days=20)
    make_batch(variant, "LATER", 10, best_before_days=300)
    assert [b.batch_code for b, _ in batches_nearing_expiry()] == ["SOON"]


# ------------------------------------------------------------------ reservations

@pytest.mark.django_db
def test_a_reservation_reduces_available_but_not_on_hand(variant):
    make_batch(variant, "B1", 10)
    reserve(variant, 3, cart_id="c1")
    assert on_hand_qty(variant) == 10
    assert available_qty(variant) == 7


@pytest.mark.django_db
def test_reserving_more_than_available_fails_and_holds_nothing(variant):
    make_batch(variant, "B1", 5)
    with pytest.raises(InsufficientStock):
        reserve(variant, 6, cart_id="c1")
    assert StockReservation.objects.count() == 0
    assert available_qty(variant) == 5


@pytest.mark.django_db
def test_expired_reservations_release_stock(variant):
    make_batch(variant, "B1", 10)
    reservations = reserve(variant, 4, cart_id="c1", ttl_minutes=30)
    StockReservation.objects.filter(pk__in=[r.pk for r in reservations]).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert expire_due_reservations() == 1
    assert available_qty(variant) == 10
    assert on_hand_qty(variant) == 10


@pytest.mark.django_db
def test_consuming_an_order_decrements_the_right_batch_exactly_once(variant, make_order):
    soon = make_batch(variant, "SOON", 4, best_before_days=60)
    late = make_batch(variant, "LATE", 10, best_before_days=365)
    order = make_order()

    reserve(variant, 6, cart_id="c1", order=order)
    movements = consume_for_order(order)
    assert len(movements) == 2
    assert batch_on_hand(soon) == 0
    assert batch_on_hand(late) == 8
    assert on_hand_qty(variant) == 8

    # Running it again must not decrement a second time.
    assert consume_for_order(order) == []
    assert on_hand_qty(variant) == 8


@pytest.mark.django_db
def test_releasing_an_order_returns_stock(variant, make_order):
    make_batch(variant, "B1", 10)
    order = make_order()
    reserve(variant, 4, cart_id="c1", order=order)
    assert available_qty(variant) == 6
    release_for_order(order)
    assert available_qty(variant) == 10
    assert on_hand_qty(variant) == 10


# ------------------------------------------------------------------ channel seam

@pytest.mark.django_db
def test_only_the_website_adapter_is_implemented(variant):
    assert registered_channels() == [Channel.WEBSITE]
    adapter = get_adapter(Channel.WEBSITE)
    make_batch(variant, "B1", 10)
    assert adapter.available(variant) == 10
    with pytest.raises(LookupError):
        get_adapter(Channel.AMAZON)


@pytest.mark.django_db
def test_a_new_channel_can_be_added_without_touching_the_ledger(variant, make_order):
    """The seam exists: registering an adapter is all a future marketplace needs."""

    @register_adapter
    class _OfflineAdapter(ChannelAdapter):
        channel = Channel.OFFLINE

        def available(self, v):
            return available_qty(v)

        def reserve(self, v, quantity, **kwargs):
            return reserve(v, quantity, **kwargs)

        def confirm(self, order, **kwargs):
            return consume_for_order(order, channel=self.channel, **kwargs)

        def cancel(self, order, **kwargs):
            return release_for_order(order, **kwargs)

    try:
        make_batch(variant, "B1", 10)
        order = make_order()
        adapter = get_adapter(Channel.OFFLINE)
        adapter.reserve(variant, 2, cart_id="offline-1", order=order)
        adapter.confirm(order)
        assert StockMovement.objects.filter(kind=MovementKind.SALE_OUT).first().channel == Channel.OFFLINE
        assert on_hand_qty(variant) == 8
    finally:
        from inventory.adapters import _ADAPTERS

        _ADAPTERS.pop(Channel.OFFLINE, None)


# ------------------------------------------------------------------ order state machine

@pytest.mark.django_db
def test_illegal_status_transitions_are_rejected(make_order):
    order = make_order(payment_status="paid")
    with pytest.raises(OrderStateError):
        set_payment_status(order, "processing")
    set_order_status(order, "Cancelled")
    order.refresh_from_db()
    with pytest.raises(OrderStateError):
        set_order_status(order, "Fulfilled")


@pytest.mark.django_db
def test_cancelling_an_order_releases_its_stock(variant, make_order):
    make_batch(variant, "B1", 10)
    order = make_order()
    reserve(variant, 3, cart_id="c1", order=order)
    assert available_qty(variant) == 7

    cancel_order(order, reason="customer changed mind")
    order.refresh_from_db()
    assert order.order_status == "Cancelled"
    assert available_qty(variant) == 10
    assert on_hand_qty(variant) == 10


@pytest.mark.django_db
def test_unconfirmed_cod_order_cannot_be_dispatched(variant, make_order, product, vendor):
    from store.models import CartOrderItem

    make_batch(variant, "B1", 10)
    order = make_order()
    order.payment_method = "COD"
    order.save()
    item = CartOrderItem.objects.create(order=order, product=product, variant=variant, qty=1,
                                        price=Decimal("56.00"), sub_total=Decimal("56.00"),
                                        total=Decimal("56.00"), vendor=vendor)
    reserve(variant, 1, cart_id="c1", order=order)

    with pytest.raises(CODNotConfirmed):
        set_delivery_status(item, "Shipping Processing")

    item.refresh_from_db()
    assert item.delivery_status == "On Hold"
    assert on_hand_qty(variant) == 10  # stock has not left


@pytest.mark.django_db
def test_prepaid_order_dispatch_consumes_stock(variant, make_order, product, vendor):
    from store.models import CartOrderItem

    make_batch(variant, "B1", 10)
    order = make_order(payment_status="paid")
    order.payment_method = "UPI"
    order.save()
    item = CartOrderItem.objects.create(order=order, product=product, variant=variant, qty=2,
                                        price=Decimal("56.00"), sub_total=Decimal("112.00"),
                                        total=Decimal("112.00"), vendor=vendor)
    reserve(variant, 2, cart_id="c1", order=order)

    set_delivery_status(item, "Shipping Processing")
    assert on_hand_qty(variant) == 8

    # Moving further through fulfilment must not decrement again.
    set_delivery_status(item, "Shipped")
    set_delivery_status(item, "Arrived")
    set_delivery_status(item, "Delivered")
    assert on_hand_qty(variant) == 8
    item.refresh_from_db()
    assert item.product_delivered is True


# ------------------------------------------------------------------ checkout wiring

@pytest.mark.django_db
def test_adding_to_cart_holds_stock_and_refuses_more_than_available(api, product, variant):
    make_batch(variant, "B1", 3)

    ok = api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 2, "country": "India",
                                       "size": "", "color": "", "cart_id": "cart-fb-1"})
    assert ok.status_code == 201
    assert available_qty(variant) == 1

    too_many = api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 9, "country": "India",
                                             "size": "", "color": "", "cart_id": "cart-fb-2"})
    assert too_many.status_code == 400
    assert available_qty(variant) == 1


@pytest.mark.django_db
def test_changing_cart_quantity_replaces_the_hold_instead_of_stacking(api, product, variant):
    make_batch(variant, "B1", 10)
    for qty in (2, 5, 3):
        response = api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": qty,
                                                 "country": "India", "size": "", "color": "", "cart_id": "cart-fb-3"})
        assert response.status_code in (200, 201)
    active = StockReservation.objects.filter(status=ReservationStatus.ACTIVE)
    assert active.count() == 1
    assert active.first().quantity == 3
    assert available_qty(variant) == 7


@pytest.mark.django_db
def test_removing_a_cart_line_gives_the_stock_back(api, product, variant):
    from store.models import Cart

    make_batch(variant, "B1", 10)
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 4, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-fb-4"})
    assert available_qty(variant) == 6
    line = Cart.objects.get(cart_id="cart-fb-4")
    assert api.delete(f"{API}cart-delete/cart-fb-4/{line.id}/").status_code == 204
    assert available_qty(variant) == 10


@pytest.mark.django_db
def test_checkout_twice_with_the_same_cart_creates_one_order(api, product, variant):
    from store.models import CartOrder

    make_batch(variant, "B1", 10)
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 1, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-fb-5"})
    payload = {"full_name": "Asha Rao", "email": "asha@example.com", "mobile": "098765 43210",
               "address": "12 MG Road", "city": "Ludhiana", "state": "Punjab", "country": "India",
               "pincode": "141001", "payment_method": "UPI", "cart_id": "cart-fb-5"}

    first = api.post(f"{API}create-order/", payload)
    second = api.post(f"{API}create-order/", payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["order_oid"] == second.json()["order_oid"]
    assert CartOrder.objects.filter(idempotency_key="cart-fb-5").count() == 1


@pytest.mark.django_db
def test_checkout_records_pincode_payment_method_channel_and_normalised_phone(api, product, variant):
    from store.models import CartOrder

    make_batch(variant, "B1", 10)
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 1, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-fb-6"})
    api.post(f"{API}create-order/", {"full_name": "Asha Rao", "email": "asha@example.com", "mobile": "098765 43210",
                                     "address": "12 MG Road", "city": "Ludhiana", "state": "Punjab",
                                     "country": "India", "pincode": "141001", "payment_method": "cod",
                                     "cart_id": "cart-fb-6"})
    order = CartOrder.objects.get(idempotency_key="cart-fb-6")
    assert order.pincode == "141001"
    assert order.payment_method == "COD"
    assert order.channel == "WEBSITE"
    assert order.phone_e164 == "+919876543210"
    assert order.orderitem.get().variant_id == variant.id


@pytest.mark.django_db
def test_checkout_moves_the_holds_from_the_cart_to_the_order(api, product, variant):
    from store.models import CartOrder

    make_batch(variant, "B1", 10)
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 3, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-fb-7"})
    api.post(f"{API}create-order/", {"full_name": "A", "email": "a@example.com", "mobile": "9876543210",
                                     "address": "a", "city": "c", "state": "s", "country": "India",
                                     "cart_id": "cart-fb-7"})
    order = CartOrder.objects.get(idempotency_key="cart-fb-7")
    holds = StockReservation.objects.filter(status=ReservationStatus.ACTIVE)
    assert holds.count() == 1
    assert holds.first().order_id == order.id
    assert available_qty(variant) == 7


@pytest.mark.django_db
def test_invalid_payment_method_is_rejected(api, product, variant):
    make_batch(variant, "B1", 10)
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 1, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-fb-8"})
    response = api.post(f"{API}create-order/", {"full_name": "A", "email": "a@example.com", "mobile": "9876543210",
                                                "address": "a", "city": "c", "state": "s", "country": "India",
                                                "payment_method": "BITCOIN", "cart_id": "cart-fb-8"})
    assert response.status_code == 400


# ------------------------------------------------------------------ phone

def test_indian_phone_numbers_normalise_to_e164():
    for raw in ("9876543210", "098765 43210", "+91 98765-43210", "0091 9876543210", "91 9876543210"):
        assert to_e164(raw) == "+919876543210"


def test_invalid_phone_numbers_are_rejected_not_guessed():
    for raw in ("", "12345", "1234567890", "+1 415 555 0199", "abcdefghij"):
        with pytest.raises(InvalidPhoneNumber):
            to_e164(raw)
        assert try_to_e164(raw) == ""


def test_phone_masking_keeps_only_the_last_four_digits():
    assert mask("+91 98765 43210") == "***3210"
    assert mask("12") == "***"


# ------------------------------------------------------------------ concurrency

class ConcurrentCheckoutTest(TransactionTestCase):
    """
    Two concurrent buyers, one unit left: exactly one must win.

    This needs real row locking, so it is skipped on SQLite (where select_for_update is a
    no-op) rather than passing for the wrong reason.
    """

    reset_sequences = True

    def test_two_concurrent_checkouts_for_the_last_unit(self):
        if connection.vendor != "postgresql":
            self.skipTest(f"needs PostgreSQL row locking; running on {connection.vendor}")

        import threading

        from store.models import Product
        from vendor.models import Vendor
        from userauths.models import User

        owner = User.objects.create_user(email="owner@example.com", username="owner", password="x")
        shop = Vendor.objects.create(user=owner, name="Shop", slug="shop")
        product = Product.objects.create(title="Last One", price=Decimal("10.00"), shipping_amount=Decimal("0.00"),
                                         stock_qty=0, status="published", vendor=shop)
        # Creating the product creates its default variant (catalog.signals).
        variant = ProductVariant.objects.get(product=product, is_default=True)
        batch = Batch.objects.create(batch_code="RACE-1", variant=variant, manufactured_on=timezone.localdate(),
                                     best_before=None, quantity_produced=1, cost_per_unit_paise=0)
        receive_production(variant, batch, 1)

        results = []
        barrier = threading.Barrier(2)

        def attempt(cart_id):
            barrier.wait()
            try:
                with transaction.atomic():
                    reserve(variant, 1, cart_id=cart_id)
                results.append("ok")
            except InsufficientStock:
                results.append("rejected")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(f"race-{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), ["ok", "rejected"])
        self.assertEqual(available_qty(variant), 0)
        self.assertEqual(
            StockReservation.objects.filter(status=ReservationStatus.ACTIVE).count(), 1
        )
