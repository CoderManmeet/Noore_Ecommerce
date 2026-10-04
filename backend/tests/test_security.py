"""
Security regression tests for Phase F-A.

Every test here reproduces a vulnerability that was LIVE-VERIFIED against the original
codebase. They fail on the baseline commit and pass after Phase F-A.
"""

from decimal import Decimal
from unittest import mock

import pytest

API = "/api/v1/"
SENSITIVE_KEYS = {"password", "otp", "reset_token", "user_permissions", "groups", "is_superuser"}


def find_sensitive_keys(data, path="$"):
    """Recursively collect paths of any sensitive key anywhere in a JSON response."""
    hits = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in SENSITIVE_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(find_sensitive_keys(value, f"{path}.{key}"))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            hits.extend(find_sensitive_keys(value, f"{path}[{i}]"))
    return hits


# ---------------------------------------------------------------- credential leaks

@pytest.mark.django_db
def test_public_catalog_endpoints_never_expose_credentials(api, product, customer, vendor):
    from store.models import Review

    customer.otp = "1234567"
    customer.reset_token = "secret-reset-token"
    customer.save()
    vendor.user.otp = "7654321"
    vendor.user.save()
    Review.objects.create(user=customer, product=product, rating=5, review="Great", active=True)

    urls = [
        f"{API}products/",
        f"{API}featured-products/",
        f"{API}products/{product.slug}/",
        f"{API}reviews/{product.id}/",
        f"{API}shop/{vendor.slug}/",
        f"{API}vendor-products/{vendor.slug}/",
        f"{API}search/?query=Test",
    ]
    for url in urls:
        response = api.get(url)
        assert response.status_code == 200, url
        assert find_sensitive_keys(response.json()) == [], url


@pytest.mark.django_db
def test_reviews_do_not_expose_reviewer_email_or_phone(api, product, customer):
    from store.models import Review

    Review.objects.create(user=customer, product=product, rating=4, review="Nice", active=True)
    body = api.get(f"{API}reviews/{product.id}/").json()
    text = str(body)
    assert customer.email not in text
    assert customer.phone not in text


@pytest.mark.django_db
def test_checkout_of_guest_order_does_not_expose_credentials(api, make_order, customer):
    order = make_order(buyer=None)
    response = api.get(f"{API}checkout/{order.oid}/")
    assert response.status_code == 200
    assert find_sensitive_keys(response.json()) == []


# ---------------------------------------------------------------- account takeover

@pytest.mark.django_db
def test_profile_endpoint_is_owner_only(api, auth, customer, other_customer):
    url = f"{API}user/profile/{customer.id}/"
    assert api.get(url).status_code == 401
    assert auth(other_customer).get(url).status_code == 403
    response = auth(customer).get(url)
    assert response.status_code == 200
    assert find_sensitive_keys(response.json()) == []


@pytest.mark.django_db
def test_password_reset_request_returns_no_account_data(api, customer):
    known = api.get(f"{API}user/password-reset/{customer.email}/")
    unknown = api.get(f"{API}user/password-reset/nobody-here@example.com/")
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
    assert find_sensitive_keys(known.json()) == []
    assert "id" not in known.json()


@pytest.mark.django_db
def test_password_change_rejects_otp_without_valid_reset_token(api, customer):
    customer.otp = "1234567"
    customer.reset_token = ""
    customer.save()
    response = api.post(f"{API}user/password-change/", {
        "otp": "1234567", "uidb64": str(customer.id), "reset_token": "forged", "password": "N3w!Passw0rd-xyz",
    })
    assert response.status_code == 400
    customer.refresh_from_db()
    assert not customer.check_password("N3w!Passw0rd-xyz")


@pytest.mark.django_db
def test_password_reset_full_flow_is_single_use(api, customer, mailoutbox):
    api.get(f"{API}user/password-reset/{customer.email}/")
    customer.refresh_from_db()
    assert len(mailoutbox) == 1
    assert customer.otp and customer.reset_token
    payload = {"otp": customer.otp, "uidb64": str(customer.id), "reset_token": customer.reset_token,
               "password": "N3w!Passw0rd-xyz"}

    first = api.post(f"{API}user/password-change/", payload)
    assert first.status_code == 201
    customer.refresh_from_db()
    assert customer.check_password("N3w!Passw0rd-xyz")

    payload["password"] = "An0ther!Passw0rd-abc"
    second = api.post(f"{API}user/password-change/", payload)
    assert second.status_code == 400
    customer.refresh_from_db()
    assert customer.check_password("N3w!Passw0rd-xyz")


# ---------------------------------------------------------------- IDOR on customer data

@pytest.mark.django_db
def test_customer_orders_are_owner_only(api, auth, customer, other_customer, make_order):
    order = make_order(buyer=customer, payment_status="paid")
    list_url = f"{API}customer/orders/{customer.id}/"
    detail_url = f"{API}customer/order/detail/{customer.id}/{order.oid}/"

    assert api.get(list_url).status_code == 401
    assert auth(other_customer).get(list_url).status_code == 403
    assert auth(other_customer).get(detail_url).status_code == 403
    mine = auth(customer).get(list_url)
    assert mine.status_code == 200 and len(mine.json()) == 1
    assert auth(customer).get(detail_url).status_code == 200


@pytest.mark.django_db
def test_wishlist_notifications_and_settings_are_owner_only(api, auth, customer, other_customer, product):
    for url in (f"{API}customer/wishlist/{customer.id}/", f"{API}customer/notification/{customer.id}/",
                f"{API}customer/setting/{customer.id}/"):
        assert api.get(url).status_code == 401, url
        assert auth(other_customer).get(url).status_code == 403, url
        assert auth(customer).get(url).status_code == 200, url

    hijack = auth(other_customer).patch(f"{API}customer/setting/{customer.id}/", {"full_name": "Hacked"})
    assert hijack.status_code == 403

    add_for_victim = auth(other_customer).post(f"{API}customer/wishlist/create/",
                                               {"product_id": product.id, "user_id": customer.id})
    assert add_for_victim.status_code == 403


@pytest.mark.django_db
def test_settings_update_changes_the_callers_own_profile(auth, customer):
    response = auth(customer).patch(f"{API}customer/setting/{customer.id}/", {"full_name": "Asha R"})
    assert response.status_code == 200
    customer.profile.refresh_from_db()
    assert customer.profile.full_name == "Asha R"


@pytest.mark.django_db
def test_registered_buyers_order_is_hidden_from_other_users(api, auth, customer, other_customer, make_order):
    order = make_order(buyer=customer)
    url = f"{API}checkout/{order.oid}/"
    assert auth(other_customer).get(url).status_code == 403
    assert api.get(url).status_code == 403
    assert auth(customer).get(url).status_code == 200


# ---------------------------------------------------------------- price tampering

@pytest.mark.django_db
def test_cart_price_and_shipping_come_from_the_database(api, product):
    response = api.post(f"{API}cart-view/", {
        "product": product.id, "user": "undefined", "qty": 2, "price": "1.00", "shipping_amount": "0",
        "country": "India", "size": "", "color": "", "cart_id": "cart-test-1",
    })
    assert response.status_code == 201
    from store.models import Cart

    line = Cart.objects.get(cart_id="cart-test-1")
    assert line.price == Decimal("56.00")
    assert line.sub_total == Decimal("112.00")
    assert line.price_paise == 5600
    assert line.sub_total_paise == 11200
    # G1: shipping is one flat charge per order from store.pricing.quote(), never a per-line
    # amount, and never the figure the client sent ("0").
    assert line.shipping_amount == Decimal("0.00")
    totals = api.get(f"{API}cart-detail/cart-test-1/").json()
    assert totals["subtotal_paise"] == 11200
    assert totals["shipping_paise"] == 7900
    assert totals["total_paise"] == 19100


@pytest.mark.django_db
def test_cart_cannot_be_created_for_another_user(auth, customer, other_customer, product):
    response = auth(other_customer).post(f"{API}cart-view/", {
        "product": product.id, "user": customer.id, "qty": 1, "price": "56.00", "shipping_amount": "3.00",
        "country": "India", "size": "", "color": "", "cart_id": "cart-test-2",
    })
    assert response.status_code == 403


@pytest.mark.django_db
def test_order_cannot_be_created_on_behalf_of_another_user(api, customer, product):
    api.post(f"{API}cart-view/", {"product": product.id, "user": "undefined", "qty": 1, "country": "India",
                                  "size": "", "color": "", "cart_id": "cart-test-3"})
    response = api.post(f"{API}create-order/", {
        "full_name": "X", "email": "x@example.com", "mobile": "9876543210", "address": "a", "city": "c",
        "state": "s", "country": "India", "cart_id": "cart-test-3", "user_id": customer.id,
    })
    assert response.status_code == 403


# ---------------------------------------------------------------- reviews

@pytest.mark.django_db
def test_review_requires_login_and_is_written_as_the_caller(api, auth, customer, other_customer, product,
                                                            delivered_order):
    from store.models import Review

    # G4: only a customer who has received the product may review it.
    delivered_order(other_customer)

    anon = api.post(f"{API}create-review/", {"user_id": customer.id, "product_id": product.id, "rating": 1, "review": "x"})
    assert anon.status_code == 401

    impersonate = auth(other_customer).post(f"{API}create-review/", {
        "user_id": customer.id, "product_id": product.id, "rating": 1, "review": "x"})
    assert impersonate.status_code == 403
    assert Review.objects.count() == 0

    own = auth(other_customer).post(f"{API}create-review/", {"product_id": product.id, "rating": 5, "review": "Good"})
    assert own.status_code == 201
    assert Review.objects.get().user_id == other_customer.id


# ---------------------------------------------------------------- owner dashboard

@pytest.mark.django_db
def test_owner_dashboard_endpoints_are_staff_only(api, auth, customer, staff, vendor, product):
    urls = [
        f"{API}vendor/stats/{vendor.id}/",
        f"{API}vendor/products/{vendor.id}/",
        f"{API}vendor/orders/{vendor.id}/",
        f"{API}vendor-coupon-list/{vendor.id}/",
        f"{API}vendor-earning/{vendor.id}/",
        f"{API}vendor-orders-report-chart/{vendor.id}/",
        f"{API}vendor-notifications-summary/{vendor.id}/",
    ]
    for url in urls:
        assert api.get(url).status_code == 401, url
        assert auth(customer).get(url).status_code == 403, url
        assert auth(staff).get(url).status_code == 200, url


@pytest.mark.django_db
def test_anonymous_users_cannot_create_products_or_coupons(api, vendor):
    from store.models import Coupon, Product

    before_products = Product.objects.count()
    assert api.post(f"{API}vendor-product-create/{vendor.id}/", {"title": "Spam", "price": "1"}).status_code == 401
    assert api.post(f"{API}vendor-coupon-create/{vendor.id}/", {
        "vendor_id": vendor.id, "code": "FREE", "discount": 100, "active": "true"}).status_code == 401
    assert Product.objects.count() == before_products
    assert not Coupon.objects.filter(code="FREE").exists()


@pytest.mark.django_db
def test_public_shop_page_is_readable_but_not_writable(api, vendor):
    url = f"{API}shop/{vendor.slug}/"
    assert api.get(url).status_code == 200
    assert api.patch(url, {"name": "Hijacked"}).status_code == 401
    vendor.refresh_from_db()
    assert vendor.name == "House Brand"


# ---------------------------------------------------------------- payment confirmation replay

@pytest.mark.django_db
def test_stripe_session_from_another_order_cannot_mark_order_paid(api, make_order, legacy_providers):
    order = make_order()
    order.stripe_session_id = "cs_test_belongs_to_this_order"
    order.save()
    response = api.post(f"{API}payment-success/", {
        "order_oid": order.oid, "session_id": "cs_test_some_other_paid_session", "payapl_order_id": "null"})
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.payment_status == "processing"


def _paypal_mocks(amount_value, currency="USD", status="COMPLETED"):
    token_response = mock.Mock(status_code=200)
    token_response.json.return_value = {"access_token": "test-access-token"}
    order_response = mock.Mock(status_code=200)
    order_response.json.return_value = {
        "status": status,
        "purchase_units": [{"amount": {"currency_code": currency, "value": amount_value}}],
    }
    return token_response, order_response


@pytest.mark.django_db
def test_paypal_order_id_cannot_be_replayed_against_a_second_order(api, make_order, legacy_providers):
    first = make_order(total=Decimal("59.00"))
    second = make_order(total=Decimal("59.00"))
    token_response, order_response = _paypal_mocks("59.00")
    with mock.patch("store.views.PAYPAL_CLIENT_ID", "cid"), mock.patch("store.views.PAYPAL_SECRET_ID", "sec"), \
            mock.patch("store.views.requests.post", return_value=token_response), \
            mock.patch("store.views.requests.get", return_value=order_response):
        ok = api.post(f"{API}payment-success/", {"order_oid": first.oid, "session_id": "null", "payapl_order_id": "PAYPAL-1"})
        replay = api.post(f"{API}payment-success/", {"order_oid": second.oid, "session_id": "null", "payapl_order_id": "PAYPAL-1"})
    assert ok.status_code == 201
    assert replay.status_code == 409
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.payment_status == "paid"
    assert second.payment_status == "processing"


@pytest.mark.django_db
def test_paypal_payment_for_a_smaller_amount_is_rejected(api, make_order, legacy_providers):
    order = make_order(total=Decimal("590.00"))
    token_response, order_response = _paypal_mocks("1.00")
    with mock.patch("store.views.PAYPAL_CLIENT_ID", "cid"), mock.patch("store.views.PAYPAL_SECRET_ID", "sec"), \
            mock.patch("store.views.requests.post", return_value=token_response), \
            mock.patch("store.views.requests.get", return_value=order_response):
        response = api.post(f"{API}payment-success/", {"order_oid": order.oid, "session_id": "null", "payapl_order_id": "PAYPAL-2"})
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.payment_status == "processing"
