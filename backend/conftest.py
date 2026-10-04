import itertools
from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

_counter = itertools.count(1)


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _isolated_media_root(settings, tmp_path):
    """Tests must never write uploads into backend/media/: every test gets a throwaway MEDIA_ROOT."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def _money_mirrors_never_drift():
    """
    ROADMAP G1 mirror check (A5): after EVERY save of a Cart, CartOrder or CartOrderItem in
    the whole test suite, walk every money column pair and prove
    to_paise(decimal_column) == paise_column. A drift fails the test that caused it.
    """
    from django.db.models.signals import post_save

    from store.models import Cart, CartOrder, CartOrderItem
    from store.money_mirror import assert_mirrors

    def _check(sender, instance, **kwargs):
        assert_mirrors(instance)

    models = (Cart, CartOrder, CartOrderItem)
    for model in models:
        post_save.connect(_check, sender=model, weak=False, dispatch_uid=f"test_mirror_{model.__name__}")
    yield
    for model in models:
        post_save.disconnect(sender=model, dispatch_uid=f"test_mirror_{model.__name__}")


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    from userauths.models import User

    def _make(staff=False, password="Str0ng!Passw0rd", **extra):
        n = next(_counter)
        user = User(email=f"user{n}@example.com", username=f"user{n}", full_name=f"User {n}", phone=f"98765{n:05d}", **extra)
        user.is_staff = staff
        user.set_password(password)
        user.save()
        return user

    return _make


@pytest.fixture
def customer(make_user):
    return make_user()


@pytest.fixture
def other_customer(make_user):
    return make_user()


@pytest.fixture
def staff(make_user):
    return make_user(staff=True)


@pytest.fixture
def auth(api):
    """auth(user) -> APIClient authenticated as `user` with a real JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken

    def _auth(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    return _auth


@pytest.fixture
def vendor(staff):
    from vendor.models import Vendor

    return Vendor.objects.create(user=staff, name="House Brand", email="shop@example.com", slug="house-brand")


@pytest.fixture
def config_settings(db):
    from addon.models import ConfigSettings

    return ConfigSettings.objects.create(service_fee_percentage=0, service_fee_charge_type="percentage")


@pytest.fixture
def product(vendor, config_settings):
    """
    A published product with a default variant and 10 units of unexpiring opening stock.

    Creating a Product creates its default variant and opening batch automatically
    (catalog.signals), exactly as it does for a product added from the owner dashboard.
    """
    from store.models import Product

    return Product.objects.create(
        title="Test Product", price=Decimal("56.00"), old_price=Decimal("60.00"),
        shipping_amount=Decimal("3.00"), stock_qty=10, status="published", vendor=vendor,
    )


@pytest.fixture
def make_order(db):
    from store.models import CartOrder

    def _make(buyer=None, total=Decimal("59.00"), payment_status="processing"):
        return CartOrder.objects.create(
            buyer=buyer, full_name="Asha Rao", email="asha@example.com", mobile="9876543210",
            address="12 MG Road", city="Ludhiana", state="Punjab", country="India",
            total=total, sub_total=total, payment_status=payment_status,
        )

    return _make


@pytest.fixture
def legacy_providers(settings):
    """Stripe and PayPal are switched off by default from G3; tests of that legacy code turn them on."""
    settings.ENABLED_PAYMENT_PROVIDERS = ["razorpay", "cod", "stripe", "paypal"]


@pytest.fixture
def delivered_order(db, product, make_order):
    """delivered_order(user) -> a paid order of the `product` fixture whose line has been delivered."""
    from catalog.models import ProductVariant
    from store.models import CartOrderItem

    def _make(user, product_=None):
        target = product_ or product
        variant = ProductVariant.objects.get(product=target, is_default=True)
        order = make_order(buyer=user, payment_status="paid")
        CartOrderItem.objects.create(order=order, product=target, variant=variant, qty=1,
                                     price=Decimal("56.00"), sub_total=Decimal("56.00"), total=Decimal("56.00"),
                                     delivery_status="Delivered")
        return order

    return _make
