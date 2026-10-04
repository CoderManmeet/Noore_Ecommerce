"""
Phase G4 tests: verified-buyer reviews with owner moderation, the single review-request
email, and one-tap reorder.

Every test here fails before Phase G4 (reviews were unmoderated and not tied to a purchase;
there was no reorder endpoint) and passes after it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import ProductVariant
from core.jobs import run_due_jobs
from core.models import AuditLog, Job
from inventory.services import available_qty
from store.jobs import queue_review_requests
from store.models import Cart, CartOrder, CartOrderItem, Product, Review
from tests.test_pricing import add_stock, make_candle

API = "/api/v1/"


def review(client, product, rating=5, text="Lovely"):
    return client.post(f"{API}create-review/", {"product_id": product.id, "rating": rating, "review": text})


# --------------------------------------------------------------------------- reviews

@pytest.mark.django_db
def test_only_a_customer_with_a_delivered_line_can_review(auth, customer, other_customer, product, delivered_order, make_order):
    # Never bought it.
    assert review(auth(customer), product).status_code == 403

    # Bought it, but it has not been delivered yet.
    variant = ProductVariant.objects.get(product=product, is_default=True)
    pending = make_order(buyer=customer, payment_status="paid")
    CartOrderItem.objects.create(order=pending, product=product, variant=variant, qty=1, price=Decimal("56.00"),
                                 sub_total=Decimal("56.00"), total=Decimal("56.00"), delivery_status="Shipped")
    assert review(auth(customer), product).status_code == 403

    # Someone else's delivered order does not count.
    delivered_order(other_customer)
    assert review(auth(customer), product).status_code == 403
    assert Review.objects.count() == 0

    delivered = delivered_order(customer)
    response = review(auth(customer), product)
    assert response.status_code == 201 and response.json()["status"] == "PENDING"
    saved = Review.objects.get()
    assert (saved.user_id, saved.status, saved.active) == (customer.id, "PENDING", False)
    assert saved.order_item.order_id == delivered.id


@pytest.mark.django_db
def test_pending_and_rejected_reviews_are_never_public_and_never_affect_the_average(api, auth, staff, customer, other_customer,
                                                                                    product, delivered_order):
    delivered_order(customer)
    delivered_order(other_customer)
    review(auth(customer), product, rating=1, text="Arrived broken")
    review(auth(other_customer), product, rating=5, text="Great")
    one_star, five_star = Review.objects.order_by("id")

    def public():
        listing = api.get(f"{API}reviews/{product.id}/").json()
        detail = api.get(f"{API}products/{product.slug}/").json()
        return [r["review"] for r in listing], detail["product_rating"], detail["rating_count"]

    assert public() == ([], None, 0)  # both PENDING

    owner = auth(staff)
    queue = owner.get(f"{API}owner/reviews/").json()
    assert {r["id"] for r in queue} == {one_star.id, five_star.id}

    assert owner.post(f"{API}owner/reviews/{five_star.id}/moderate/", {"action": "approve"}).status_code == 200
    assert public() == (["Great"], 5.0, 1)

    # A low rating is a legitimate review: approving it moves the average.
    owner.post(f"{API}owner/reviews/{one_star.id}/moderate/", {"action": "approve"})
    assert public()[1:] == (3.0, 2)

    owner.post(f"{API}owner/reviews/{one_star.id}/moderate/", {"action": "reject", "reason": "abusive language"})
    assert public() == (["Great"], 5.0, 1)

    one_star.refresh_from_db()
    assert (one_star.status, one_star.moderated_by_id, one_star.active) == ("REJECTED", staff.id, False)
    assert one_star.moderated_at is not None
    audits = AuditLog.objects.filter(action="review.moderated", object_id=str(one_star.id)).order_by("id")
    assert [(a.before["status"], a.after["status"], a.actor_id) for a in audits] == [
        ("PENDING", "APPROVED", staff.id), ("APPROVED", "REJECTED", staff.id)]
    assert owner.get(f"{API}owner/reviews/").json() == []
    assert len(owner.get(f"{API}owner/reviews/?status=all").json()) == 2

    # Public reviews expose a name and avatar only.
    body = api.get(f"{API}reviews/{product.id}/").content.decode()
    assert other_customer.email not in body and "password" not in body


@pytest.mark.django_db
def test_a_second_review_for_the_same_product_is_refused(auth, customer, product, delivered_order):
    delivered_order(customer)
    delivered_order(customer)  # two orders of the same product still mean one review
    assert review(auth(customer), product).status_code == 201
    again = review(auth(customer), product, text="Another one")
    assert again.status_code == 400
    assert Review.objects.count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(user=customer, product=product, rating=3, review="direct write")


@pytest.mark.django_db
def test_moderation_is_staff_only(api, auth, customer, product, delivered_order):
    delivered_order(customer)
    review(auth(customer), product)
    target = Review.objects.get()
    assert api.post(f"{API}owner/reviews/{target.id}/moderate/", {"action": "approve"}).status_code == 401
    assert auth(customer).post(f"{API}owner/reviews/{target.id}/moderate/", {"action": "approve"}).status_code == 403
    assert auth(customer).get(f"{API}owner/reviews/").status_code == 403
    target.refresh_from_db()
    assert target.status == "PENDING"


@pytest.mark.django_db
def test_the_review_form_is_only_offered_to_eligible_customers(api, auth, customer, product, delivered_order):
    url = f"{API}review-eligibility/{product.id}/"
    assert api.get(url).json() == {"eligible": False, "reason": "login"}
    assert auth(customer).get(url).json() == {"eligible": False, "reason": "not_purchased"}
    delivered_order(customer)
    assert auth(customer).get(url).json() == {"eligible": True, "reason": ""}
    review(auth(customer), product)
    assert auth(customer).get(url).json() == {"eligible": False, "reason": "already_reviewed"}


@pytest.mark.django_db
def test_one_review_request_email_is_sent_a_set_number_of_days_after_delivery(customer, delivered_order, mailoutbox, settings):
    settings.REVIEW_REQUEST_DELAY_DAYS = 7
    order = delivered_order(customer)

    CartOrder.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=6))
    assert queue_review_requests() == 0

    CartOrder.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=8))
    queue_review_requests()
    queue_review_requests()  # every later run: still the one email
    run_due_jobs()
    queue_review_requests()
    run_due_jobs()

    assert Job.objects.filter(name="store.send_order_email", payload__kind="review_request").count() == 1
    requests = [m for m in mailoutbox if "How was your order" in m.subject]
    assert len(requests) == 1 and requests[0].to == ["asha@example.com"]

    undelivered = delivered_order(customer)  # delivered_at never stamped: no email
    assert undelivered.delivered_at is None
    assert queue_review_requests() == 1  # only the first order is in the window


# --------------------------------------------------------------------------- reorder

@pytest.fixture
def three_line_order(vendor, config_settings, customer, make_order):
    a = make_candle(vendor, "Vanilla", 49900, stock=10)
    b = make_candle(vendor, "Sandal", 79900, stock=10)
    c = make_candle(vendor, "Lavender", 119900, stock=0)  # sold out today
    order = make_order(buyer=customer, payment_status="paid")
    for variant, qty, old_price in ((a, 2, "450.00"), (b, 1, "700.00"), (c, 1, "999.00")):
        CartOrderItem.objects.create(order=order, product=variant.product, variant=variant, qty=qty,
                                     price=Decimal(old_price), sub_total=Decimal(old_price) * qty,
                                     total=Decimal(old_price) * qty, delivery_status="Delivered")
    return order, a, b, c


@pytest.mark.django_db
def test_reorder_adds_what_is_available_at_todays_prices_and_reports_the_rest(auth, customer, three_line_order):
    order, a, b, c = three_line_order
    client = auth(customer)
    orders_before = CartOrder.objects.count()

    response = client.post(f"{API}reorder/{order.oid}/", {"cart_id": "again-1"})
    assert response.status_code == 200
    body = response.json()

    assert [(line["title"], line["qty"]) for line in body["added"]] == [("Vanilla", 2), ("Sandal", 1)]
    assert body["reduced"] == []
    assert body["unavailable"] == [{"title": "Lavender", "wanted": 1, "reason": "sold_out"}]

    # Today's prices, not the old order's (Rs 450 and Rs 700).
    assert [line["unit_price_paise"] for line in body["added"]] == [49900, 79900]
    lines = {line.variant_id: line for line in Cart.objects.filter(cart_id="again-1")}
    assert set(lines) == {a.id, b.id}
    assert (lines[a.id].qty, lines[a.id].price_paise, lines[b.id].price_paise) == (2, 49900, 79900)
    totals = client.get(f"{API}cart-detail/again-1/{customer.id}/").json()
    assert totals["subtotal_paise"] == 2 * 49900 + 79900

    # Through the normal cart path: the stock is held. And no order was placed.
    assert (available_qty(a), available_qty(b)) == (8, 9)
    assert CartOrder.objects.count() == orders_before

    # Pressing "Buy again" twice does not double the cart or the holds.
    client.post(f"{API}reorder/{order.oid}/", {"cart_id": "again-1"})
    assert Cart.objects.filter(cart_id="again-1").count() == 2 and available_qty(a) == 8


@pytest.mark.django_db
def test_reorder_reduces_short_lines_and_skips_discontinued_ones(auth, customer, three_line_order):
    order, a, b, c = three_line_order
    add_stock(c, 5)
    from inventory.services import reserve
    reserve(a, 9, cart_id="another-shopper")          # only 1 Vanilla left; the order had 2
    b.active = False                                   # Sandal discontinued
    b.save()

    body = auth(customer).post(f"{API}reorder/{order.oid}/", {"cart_id": "again-2"}).json()
    assert [(l["title"], l["qty"], l["wanted"]) for l in body["reduced"]] == [("Vanilla", 1, 2)]
    assert [(l["title"], l["qty"]) for l in body["added"]] == [("Lavender", 1)]
    assert body["unavailable"] == [{"title": "Sandal", "wanted": 1, "reason": "discontinued"}]


@pytest.mark.django_db
def test_reorder_is_only_for_the_orders_owner(api, auth, customer, other_customer, three_line_order, make_order):
    order, *_ = three_line_order
    assert auth(other_customer).post(f"{API}reorder/{order.oid}/", {"cart_id": "x"}).status_code == 403
    assert api.post(f"{API}reorder/{order.oid}/", {"cart_id": "x"}).status_code == 403
    guest_order = make_order(payment_status="paid")
    assert api.post(f"{API}reorder/{guest_order.oid}/", {"cart_id": "x"}).status_code == 403
    assert auth(customer).post(f"{API}reorder/{order.oid}/", {}).status_code == 400
    assert Cart.objects.count() == 0
