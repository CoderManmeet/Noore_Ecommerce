"""
Phase G3 tests: Razorpay (test-mode shapes from the published documentation), Cash on
Delivery, dispatch, order emails and the guest account link.

No test talks to Razorpay: the HTTP call is replaced by a stub that returns the documented
order entity, and webhooks are signed here with the test webhook secret exactly as the
documentation describes (HMAC-SHA256 of the raw body, hex).

Every test here fails before Phase G3 (store.payments, the endpoints and the order fields did
not exist) and passes after it.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from core.jobs import run_due_jobs
from core.models import AuditLog, Job
from inventory.models import ReservationStatus, StockReservation
from inventory.services import available_qty, expire_due_reservations, on_hand_qty
from store.jobs import expire_stale_order_drafts, reconcile_pending_payments
from store.models import Cart, CartOrder
from store.money_mirror import assert_mirrors
from store.order_state import CODNotConfirmed, OrderStateError, advance_order_delivery
from tests.test_pricing import add_to_cart, create_order, make_candle
from userauths.models import User

API = "/api/v1/"
KEY_ID = "rzp_test_unitTestKeyId"
KEY_SECRET = "unit-test-key-secret-never-real"
WEBHOOK_SECRET = "unit-test-webhook-secret-0123456789abcdef"
RZP_ORDER = "order_TestG3aaaa1111"
RZP_PAYMENT = "pay_TestG3bbbb2222"


@pytest.fixture
def razorpay_keys(settings):
    settings.RAZORPAY_KEY_ID = KEY_ID
    settings.RAZORPAY_KEY_SECRET = KEY_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.ENABLED_PAYMENT_PROVIDERS = ["razorpay", "cod"]


@pytest.fixture
def candle(vendor, config_settings):
    return make_candle(vendor, "Candle", 79900, stock=10)


def draft(client, variant, qty=1, cart_id="g3-cart", **overrides):
    add_to_cart(client, variant, qty, cart_id)
    return CartOrder.objects.get(oid=create_order(client, cart_id, **overrides).json()["order_oid"])


def api_response(body, status_code=200):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = body
    return response


def order_entity(amount, order_id=RZP_ORDER, status="created", amount_paid=0):
    """The order entity as documented in Razorpay's Create Order response."""
    return {"id": order_id, "entity": "order", "amount": amount, "amount_paid": amount_paid,
            "amount_due": amount - amount_paid, "currency": "INR", "receipt": "x", "status": status,
            "attempts": 0, "notes": {}, "created_at": 1642662092}


def start(client, order, remote=None):
    with mock.patch("store.payments.razorpay.requests.request",
                    return_value=api_response(remote or order_entity(order.total_paise))) as call:
        response = client.post(f"{API}payments/razorpay/start/{order.oid}/")
    return response, call


def captured_event(order_id=RZP_ORDER, amount=87800, currency="INR", payment_id=RZP_PAYMENT, event="payment.captured"):
    return {"entity": "event", "event": event, "contains": ["payment"], "created_at": 1700000000,
            "payload": {"payment": {"entity": {"id": payment_id, "entity": "payment", "amount": amount,
                                               "currency": currency, "status": "captured", "order_id": order_id}}}}


def post_webhook(client, event, secret=WEBHOOK_SECRET, signature=None, event_id="evt_1"):
    body = json.dumps(event).encode()
    if signature is None:
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"HTTP_X_RAZORPAY_EVENT_ID": event_id}
    if signature != "":
        headers["HTTP_X_RAZORPAY_SIGNATURE"] = signature
    return client.post(f"{API}payments/razorpay/webhook/", data=body, content_type="application/json", **headers)


def email_jobs(kind=None):
    jobs = Job.objects.filter(name="store.send_order_email")
    return [j for j in jobs if kind is None or j.payload.get("kind") == kind]


# --------------------------------------------------------------------------- starting a payment

@pytest.mark.django_db
def test_start_creates_a_razorpay_order_for_the_stored_paise_total(api, candle, razorpay_keys):
    order = draft(api, candle)
    response, call = start(api, order)

    assert response.status_code == 200
    method, url = call.call_args.args
    assert (method, url) == ("POST", "https://api.razorpay.com/v1/orders")
    assert call.call_args.kwargs["auth"] == (KEY_ID, KEY_SECRET)
    sent = call.call_args.kwargs["json"]
    assert sent["amount"] == order.total_paise == 87800 and isinstance(sent["amount"], int)
    assert sent["currency"] == "INR"
    assert sent["receipt"] == order.oid

    options = response.json()["options"]
    assert options["key"] == KEY_ID
    assert (options["order_id"], options["amount"], options["currency"]) == (RZP_ORDER, 87800, "INR")
    assert options["prefill"]["contact"] == "+919876543210"
    assert KEY_SECRET not in response.content.decode() and WEBHOOK_SECRET not in response.content.decode()

    order.refresh_from_db()
    assert (order.razorpay_order_id, order.payment_provider, order.payment_status) == (RZP_ORDER, "razorpay", "processing")


@pytest.mark.django_db
def test_start_reuses_the_razorpay_order_until_the_total_changes(api, candle, razorpay_keys, vendor):
    from store.models import Coupon

    order = draft(api, candle)
    start(api, order)
    order.refresh_from_db()

    again, call = start(api, order)  # same total: the existing Razorpay order is fetched, not re-created
    assert [c.args[0] for c in call.call_args_list] == ["GET"]
    assert again.json()["options"]["order_id"] == RZP_ORDER

    Coupon.objects.create(vendor=vendor, code="TEN", discount=10, active=True)
    api.post(f"{API}coupon/", {"order_oid": order.oid, "coupon_code": "TEN"})
    order.refresh_from_db()
    replies = [api_response(order_entity(87800)), api_response(order_entity(order.total_paise, order_id="order_New"))]
    with mock.patch("store.payments.razorpay.requests.request", side_effect=replies) as call:
        changed = api.post(f"{API}payments/razorpay/start/{order.oid}/")
    assert [c.args[0] for c in call.call_args_list] == ["GET", "POST"]
    assert changed.json()["options"]["order_id"] == "order_New"
    assert changed.json()["options"]["amount"] == order.total_paise == 79900 - 7990 + 7900


@pytest.mark.django_db
def test_start_is_refused_when_not_configured_or_not_enabled(api, candle, settings):
    order = draft(api, candle)
    settings.ENABLED_PAYMENT_PROVIDERS = ["razorpay", "cod"]
    settings.RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_SECRET = ""
    assert api.post(f"{API}payments/razorpay/start/{order.oid}/").status_code == 503
    settings.ENABLED_PAYMENT_PROVIDERS = ["cod"]
    assert api.post(f"{API}payments/razorpay/start/{order.oid}/").status_code == 403
    methods = api.get(f"{API}payments/methods/").json()
    assert methods == {"razorpay": False, "razorpay_configured": False, "cod": True}


@pytest.mark.django_db
def test_a_provider_error_never_leaks_and_leaves_the_order_alone(api, candle, razorpay_keys):
    order = draft(api, candle)
    error = {"error": {"code": "BAD_REQUEST_ERROR", "description": "nope", "field": "amount"}}
    with mock.patch("store.payments.razorpay.requests.request", return_value=api_response(error, 400)):
        response = api.post(f"{API}payments/razorpay/start/{order.oid}/")
    assert response.status_code == 502
    order.refresh_from_db()
    assert order.razorpay_order_id == ""


# --------------------------------------------------------------------------- return from checkout

@pytest.mark.django_db
def test_returning_from_checkout_verifies_the_signature_but_does_not_mark_paid(api, candle, razorpay_keys):
    order = draft(api, candle)
    start(api, order)
    good = hmac.new(KEY_SECRET.encode(), f"{RZP_ORDER}|{RZP_PAYMENT}".encode(), hashlib.sha256).hexdigest()
    payload = {"order_oid": order.oid, "razorpay_order_id": RZP_ORDER, "razorpay_payment_id": RZP_PAYMENT}

    forged = api.post(f"{API}payments/razorpay/return/", {**payload, "razorpay_signature": "0" * 64})
    assert forged.status_code == 400

    # The order id signed is the one in OUR database, whatever the browser sends.
    spoofed = hmac.new(KEY_SECRET.encode(), f"order_Other|{RZP_PAYMENT}".encode(), hashlib.sha256).hexdigest()
    assert api.post(f"{API}payments/razorpay/return/",
                    {**payload, "razorpay_order_id": "order_Other", "razorpay_signature": spoofed}).status_code == 400

    ok = api.post(f"{API}payments/razorpay/return/", {**payload, "razorpay_signature": good})
    assert ok.status_code == 200 and ok.json()["message"] == "confirming"
    order.refresh_from_db()
    assert order.payment_status == "processing"  # unpaid until the webhook or the reconcile job says so
    assert order.razorpay_payment_id == RZP_PAYMENT
    assert len(email_jobs("placed")) == 1 and len(email_jobs("paid")) == 0


# --------------------------------------------------------------------------- webhook

@pytest.mark.django_db
def test_a_forged_or_unsigned_webhook_is_rejected_and_changes_nothing(api, candle, razorpay_keys):
    order = draft(api, candle)
    start(api, order)
    event = captured_event()

    assert post_webhook(api, event, signature="").status_code == 400            # unsigned
    assert post_webhook(api, event, signature="f" * 64).status_code == 400      # forged
    assert post_webhook(api, event, secret="some-other-secret").status_code == 400
    assert post_webhook(api, event, secret=KEY_SECRET).status_code == 400       # key secret is not the webhook secret

    order.refresh_from_db()
    assert order.payment_status == "processing"
    assert Job.objects.count() == 0


@pytest.mark.django_db
def test_the_same_webhook_twice_marks_paid_once_and_sends_one_email(api, candle, razorpay_keys, mailoutbox):
    order = draft(api, candle, qty=2)
    start(api, order)
    event = captured_event(amount=order.total_paise)

    first = post_webhook(api, event)
    second = post_webhook(api, event)                    # Razorpay retry of the same event
    third = post_webhook(api, event, event_id="evt_2")   # a second event for the same payment

    assert (first.status_code, first.json()["result"]) == (200, "paid")
    assert (second.status_code, second.json()["result"]) == (200, "duplicate")
    assert (third.status_code, third.json()["result"]) == (200, "duplicate")

    order.refresh_from_db()
    assert order.payment_status == "paid" and order.razorpay_payment_id == RZP_PAYMENT
    assert_mirrors(order)
    assert AuditLog.objects.filter(action="order.payment_status", object_id=str(order.pk)).count() == 1
    assert Cart.objects.filter(cart_id="g3-cart").count() == 0

    assert len(email_jobs("paid")) == 1
    run_due_jobs()
    run_due_jobs()
    paid_mails = [m for m in mailoutbox if "Payment received" in m.subject]
    assert len(paid_mails) == 1 and paid_mails[0].to == ["asha@example.com"]
    assert "₹1,598" in paid_mails[0].body and "$" not in paid_mails[0].body


@pytest.mark.django_db
def test_a_webhook_with_the_wrong_amount_or_currency_is_rejected(api, candle, razorpay_keys):
    order = draft(api, candle)
    start(api, order)
    for event in (captured_event(amount=100), captured_event(amount=order.total_paise, currency="USD")):
        response = post_webhook(api, event)
        assert (response.status_code, response.json()["result"]) == (400, "mismatch")
    order.refresh_from_db()
    assert order.payment_status == "processing"
    # A correct event afterwards still works: the bad ones claimed nothing.
    assert post_webhook(api, captured_event(amount=order.total_paise)).json()["result"] == "paid"


@pytest.mark.django_db
def test_other_events_unknown_orders_and_odd_payloads_never_mark_anything_paid(api, candle, razorpay_keys):
    order = draft(api, candle)
    start(api, order)
    assert post_webhook(api, captured_event(event="payment.authorized")).json()["result"] == "ignored"
    assert post_webhook(api, captured_event(event="payment.failed")).json()["result"] == "ignored"
    assert post_webhook(api, captured_event(order_id="order_Unknown")).json()["result"] == "unknown_order"
    assert post_webhook(api, {"event": "payment.captured", "payload": {}}).status_code == 400
    order.refresh_from_db()
    assert order.payment_status == "processing"


@pytest.mark.django_db
def test_paid_orders_keep_their_stock_and_dispatch_takes_it_from_the_ledger_exactly_once(api, staff, candle, razorpay_keys):
    order = draft(api, candle, qty=3)
    start(api, order)
    post_webhook(api, captured_event(amount=order.total_paise))
    order.refresh_from_db()

    StockReservation.objects.filter(order=order).update(created_at=timezone.now() - timedelta(days=3))
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=3)):
        assert expire_due_reservations() == 0
    assert (on_hand_qty(candle), available_qty(candle)) == (10, 7)

    advance_order_delivery(order, "Shipped", actor=staff, tracking_id="TRK1")
    assert on_hand_qty(candle) == 7
    advance_order_delivery(order, "Shipped", actor=staff)      # again: nothing more leaves
    order = advance_order_delivery(order, "Delivered", actor=staff)
    assert (on_hand_qty(candle), available_qty(candle)) == (7, 7)
    assert order.order_status == "Fulfilled" and order.delivered_at is not None
    assert order.orderitem.get().tracking_id == "TRK1"


@pytest.mark.django_db
def test_late_payment_reserves_again_or_flags_the_order_never_silently_unshippable(api, staff, vendor, candle, razorpay_keys):
    # 1. The hold lapsed but the stock is still there: reserved again, paid, shippable.
    order = draft(api, candle, qty=2, cart_id="late-1")
    start(api, order)
    StockReservation.objects.filter(order=order).update(expires_at=timezone.now() - timedelta(minutes=1))
    expire_due_reservations()
    assert post_webhook(api, captured_event(amount=order.total_paise)).json()["result"] == "paid"
    order.refresh_from_db()
    assert order.needs_attention == "" and available_qty(candle) == 8

    # 2. The hold lapsed and someone else bought the stock: paid, but flagged for a refund.
    scarce = make_candle(vendor, "Scarce", 50000, stock=1)
    late = draft(api, scarce, cart_id="late-2", email="b@example.com", mobile="9000000009")
    start(api, late, remote=order_entity(late.total_paise, order_id="order_Late2"))
    StockReservation.objects.filter(order=late).update(expires_at=timezone.now() - timedelta(minutes=1))
    expire_due_reservations()
    from inventory.services import reserve
    reserve(scarce, 1, cart_id="another-shopper")
    response = post_webhook(api, captured_event(order_id="order_Late2", amount=late.total_paise, payment_id="pay_L2"), event_id="evt_l2")
    assert response.json()["result"] == "flagged"
    late.refresh_from_db()
    assert late.payment_status == "paid" and "Refund" in late.needs_attention
    with pytest.raises(OrderStateError):
        advance_order_delivery(late, "Shipped", actor=staff)

    # 3. Payment for an order that already expired: money taken, so flagged; never marked paid.
    gone = draft(api, candle, cart_id="late-3", email="c@example.com", mobile="9000000008")
    start(api, gone, remote=order_entity(gone.total_paise, order_id="order_Late3"))
    CartOrder.objects.filter(pk=gone.pk).update(date=timezone.now() - timedelta(hours=60))
    assert expire_stale_order_drafts() == 1
    response = post_webhook(api, captured_event(order_id="order_Late3", amount=gone.total_paise, payment_id="pay_L3"), event_id="evt_l3")
    assert response.json()["result"] == "flagged"
    gone.refresh_from_db()
    assert gone.payment_status == "expired" and "Refund" in gone.needs_attention


# --------------------------------------------------------------------------- reconcile job

@pytest.mark.django_db
def test_without_a_webhook_the_order_stays_unpaid_until_the_reconcile_job_confirms_it(api, candle, razorpay_keys, settings):
    settings.PAYMENT_RECONCILE_AFTER_MINUTES = 3
    order = draft(api, candle)
    start(api, order)
    order.refresh_from_db()

    paid_remote = api_response(order_entity(order.total_paise, status="paid", amount_paid=order.total_paise))
    with mock.patch("store.payments.razorpay.requests.request", return_value=paid_remote) as call:
        assert reconcile_pending_payments() == 0          # too recent to bother Razorpay
        assert not call.called
    order.refresh_from_db()
    assert order.payment_status == "processing"

    CartOrder.objects.filter(pk=order.pk).update(date=timezone.now() - timedelta(minutes=5))
    unpaid_remote = api_response(order_entity(order.total_paise, status="attempted"))
    with mock.patch("store.payments.razorpay.requests.request", return_value=unpaid_remote):
        assert reconcile_pending_payments() == 0
    order.refresh_from_db()
    assert order.payment_status == "processing"

    short_remote = api_response(order_entity(order.total_paise, status="paid", amount_paid=100))
    with mock.patch("store.payments.razorpay.requests.request", return_value=short_remote):
        assert reconcile_pending_payments() == 0          # paid, but not in full: refused
    order.refresh_from_db()
    assert order.payment_status == "processing"

    with mock.patch("store.payments.razorpay.requests.request", return_value=paid_remote) as call:
        assert reconcile_pending_payments() == 1
        assert call.call_args.args == ("GET", f"https://api.razorpay.com/v1/orders/{RZP_ORDER}")
        assert reconcile_pending_payments() == 0          # idempotent
    order.refresh_from_db()
    assert order.payment_status == "paid"
    assert post_webhook(api, captured_event(amount=order.total_paise)).json()["result"] == "duplicate"  # late webhook
    assert len(email_jobs("paid")) == 1


# --------------------------------------------------------------------------- cash on delivery

@pytest.mark.django_db
def test_cod_order_end_to_end(api, auth, staff, customer, candle, razorpay_keys, mailoutbox):
    order = draft(api, candle, qty=2)
    placed = api.post(f"{API}payments/cod/{order.oid}/")
    assert placed.status_code == 200
    order.refresh_from_db()
    assert (order.payment_method, order.payment_provider, order.payment_status) == ("COD", "cod", "pending")
    assert Cart.objects.filter(cart_id="g3-cart").count() == 0
    assert api.post(f"{API}payments/cod/{order.oid}/").status_code == 200  # pressing twice is harmless

    # The stock is kept for the order, not subject to the cart TTL.
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=5)):
        assert expire_due_reservations() == 0
    assert available_qty(candle) == 8
    assert expire_stale_order_drafts() == 0  # a placed COD order is not a draft

    owner = auth(staff)
    action = f"{API}owner/orders/{order.oid}/action/"
    assert auth(customer).post(action, {"action": "confirm_cod"}).status_code == 403
    assert api.post(action, {"action": "confirm_cod"}).status_code == 401

    # Cannot be dispatched before "Confirm COD"...
    blocked = owner.post(action, {"action": "set_delivery", "status": "Shipped"})
    assert blocked.status_code == 409
    with pytest.raises(CODNotConfirmed):
        advance_order_delivery(order, "Shipped", actor=staff)
    assert on_hand_qty(candle) == 10

    # ...and can after.
    confirmed = owner.post(action, {"action": "confirm_cod"})
    assert confirmed.status_code == 200 and confirmed.json()["cod_confirmed_at"]
    order.refresh_from_db()
    assert order.cod_confirmed_by_id == staff.id
    audit = AuditLog.objects.get(action="order.cod_confirmed", object_id=str(order.pk))
    assert audit.actor_id == staff.id

    shipped = owner.post(action, {"action": "set_delivery", "status": "Shipped", "tracking_id": "AWB123"})
    assert shipped.status_code == 200
    assert on_hand_qty(candle) == 8
    delivered = owner.post(action, {"action": "set_delivery", "status": "Delivered"})
    assert delivered.status_code == 200 and delivered.json()["order_status"] == "Fulfilled"
    assert on_hand_qty(candle) == 8  # left the ledger exactly once

    # Cash collected: the owner marks it paid through the state machine.
    paid = owner.post(action, {"action": "mark_paid"})
    assert paid.status_code == 200 and paid.json()["payment_status"] == "paid"

    run_due_jobs()
    subjects = [m.subject for m in mailoutbox]
    assert any("We have your order" in s for s in subjects)
    assert any("on its way" in s for s in subjects)
    assert any("Payment received" in s for s in subjects)
    placed_mail = next(m for m in mailoutbox if "We have your order" in m.subject)
    assert "Cash on Delivery" in placed_mail.body and "₹1,598" in placed_mail.body
    assert "AWB123" in next(m for m in mailoutbox if "on its way" in m.subject).body
    assert len(mailoutbox) == 3


@pytest.mark.django_db
def test_cod_is_refused_cleanly_when_the_stock_has_gone_or_cod_is_switched_off(api, vendor, config_settings, settings):
    scarce = make_candle(vendor, "Scarce", 50000, stock=1)
    order = draft(api, scarce)
    StockReservation.objects.filter(order=order).update(expires_at=timezone.now() - timedelta(minutes=1))
    expire_due_reservations()
    from inventory.services import reserve
    reserve(scarce, 1, cart_id="another-shopper")

    response = api.post(f"{API}payments/cod/{order.oid}/")
    assert response.status_code == 409 and "sold out" in response.json()["message"]
    order.refresh_from_db()
    assert (order.payment_status, order.payment_method) == ("processing", "")  # rolled back completely

    settings.ENABLED_PAYMENT_PROVIDERS = ["razorpay"]
    assert api.post(f"{API}payments/cod/{order.oid}/").status_code == 403


@pytest.mark.django_db
def test_the_same_browser_cart_starts_a_new_order_after_one_is_placed(api, candle, razorpay_keys):
    first = draft(api, candle)
    api.post(f"{API}payments/cod/{first.oid}/")
    add_to_cart(api, candle, 1, "g3-cart")
    again = create_order(api, "g3-cart")
    assert again.status_code == 201
    assert again.json()["order_oid"] != first.oid


@pytest.mark.django_db
def test_owner_can_cancel_and_record_a_refund_and_customers_see_placed_orders(api, auth, staff, customer, candle, razorpay_keys):
    client = auth(customer)
    order = draft(client, candle, qty=2, user_id=customer.id)
    start(client, order)
    assert client.get(f"{API}customer/orders/{customer.id}/").json() == []  # an unpaid draft is not an order yet
    post_webhook(api, captured_event(amount=order.total_paise))
    assert [o["oid"] for o in client.get(f"{API}customer/orders/{customer.id}/").json()] == [order.oid]

    owner = auth(staff)
    listing = owner.get(f"{API}owner/orders/").json()
    assert [o["oid"] for o in listing] == [order.oid]
    assert auth(customer).get(f"{API}owner/orders/").status_code == 403

    action = f"{API}owner/orders/{order.oid}/action/"
    assert owner.post(action, {"action": "mark_paid"}).status_code == 400  # prepaid is never marked paid by hand
    cancelled = owner.post(action, {"action": "cancel", "reason": "customer asked"})
    assert cancelled.status_code == 200 and cancelled.json()["order_status"] == "Cancelled"
    assert available_qty(candle) == 10
    refunded = owner.post(action, {"action": "record_refund"})
    assert refunded.status_code == 200 and refunded.json()["payment_status"] == "refunded"
    assert len(email_jobs("cancelled")) == 1
    assert owner.post(action, {"action": "nonsense"}).status_code == 400


@pytest.mark.django_db
def test_stripe_and_paypal_are_switched_off_by_default(api, candle, settings):
    assert settings.ENABLED_PAYMENT_PROVIDERS == ["razorpay", "cod"]
    order = draft(api, candle)
    assert api.post(f"{API}stripe-checkout/{order.oid}/").status_code == 403
    assert api.post(f"{API}payment-success/", {"order_oid": order.oid, "session_id": "cs_x", "payapl_order_id": "null"}).status_code == 403
    assert api.post(f"{API}payment-success/", {"order_oid": order.oid, "session_id": "null", "payapl_order_id": "PP-1"}).status_code == 403


@pytest.mark.django_db
def test_order_oid_is_unique(make_order):
    from django.db import IntegrityError, transaction

    first = make_order()
    with pytest.raises(IntegrityError), transaction.atomic():
        CartOrder.objects.create(oid=first.oid, full_name="x", email="x@example.com", mobile="1")


# --------------------------------------------------------------------------- guest account link

@pytest.mark.django_db
def test_guest_gets_an_account_link_by_email_and_using_it_attaches_their_orders(api, candle, razorpay_keys, mailoutbox, settings):
    settings.SITE_URL = "https://shop.test"
    order = draft(api, candle, cart_id="acc-1")
    api.post(f"{API}payments/cod/{order.oid}/")
    other_same_email = draft(api, candle, cart_id="acc-2")
    api.post(f"{API}payments/cod/{other_same_email.oid}/")
    someone_else = draft(api, candle, cart_id="acc-3", email="stranger@example.com", mobile="9000000007")
    api.post(f"{API}payments/cod/{someone_else.oid}/")

    asked = api.post(f"{API}account/invite/", {"order_oid": order.oid})
    api.post(f"{API}account/invite/", {"order_oid": order.oid})  # asking twice sends one email
    unknown = api.post(f"{API}account/invite/", {"order_oid": "doesnotexist"})
    assert asked.status_code == unknown.status_code == 200 and asked.json() == unknown.json()

    run_due_jobs()
    invites = [m for m in mailoutbox if "Create your" in m.subject]
    assert len(invites) == 1 and invites[0].to == ["asha@example.com"]  # only ever the order's own address
    token = invites[0].body.split("https://shop.test/claim-account?token=")[1].split()[0]

    assert api.post(f"{API}account/claim/", {"token": "tampered" + token, "password": "Str0ng!Passw0rd"}).status_code == 400
    assert api.post(f"{API}account/claim/", {"token": token, "password": "123"}).status_code == 400
    assert User.objects.filter(email="asha@example.com").count() == 0

    from django.core.cache import cache

    cache.clear()  # these endpoints are rate-limited (5 a minute); start a fresh minute
    done = api.post(f"{API}account/claim/", {"token": token, "password": "Str0ng!Passw0rd"})
    assert done.status_code == 200 and done.json()["created"] is True and done.json()["orders_attached"] == 2
    user = User.objects.get(email="asha@example.com")
    assert user.check_password("Str0ng!Passw0rd")
    assert set(CartOrder.objects.filter(buyer=user).values_list("oid", flat=True)) == {order.oid, other_same_email.oid}
    someone_else.refresh_from_db()
    assert someone_else.buyer_id is None

    # Using the link again cannot reset the password of the account that now exists.
    again = api.post(f"{API}account/claim/", {"token": token, "password": "An0ther!Passw0rd"})
    assert again.status_code == 200 and again.json()["created"] is False
    user.refresh_from_db()
    assert user.check_password("Str0ng!Passw0rd")


@pytest.mark.django_db
def test_an_expired_account_link_is_refused(api, candle, razorpay_keys, settings):
    from store.account_claim import make_token

    order = draft(api, candle)
    api.post(f"{API}payments/cod/{order.oid}/")
    token = make_token(order)
    settings.ACCOUNT_CLAIM_LINK_HOURS = 0
    with mock.patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 3600):
        response = api.post(f"{API}account/claim/", {"token": token, "password": "Str0ng!Passw0rd"})
    assert response.status_code == 400 and "expired" in response.json()["message"]
    assert User.objects.filter(email="asha@example.com").count() == 0
