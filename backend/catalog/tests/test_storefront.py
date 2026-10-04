"""
Phase G2 tests: variant options, append-only price history, the honest strike-through and
stock indicator, read-only stock_qty, stock receipt from admin and the seed command.

Every test here fails before Phase G2 (catalog.display, PriceHistory, ProductVariant.options
and seed_noore did not exist) and passes after it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from django.utils import timezone

from catalog.display import IN_STOCK, LOW_STOCK, SOLD_OUT, lowest_prior_price, stock_status, strikethrough_for
from catalog.models import PriceHistory, ProductVariant
from core.audit import acting_as
from core.models import AppendOnlyError
from inventory.admin import BatchAdmin
from inventory.models import Batch
from inventory.services import available_qty, receive_production, reserve
from store.admin import ProductAdmin
from core.models import AuditLog
from store.models import Cart, CartOrderItem, Coupon, Product

API = "/api/v1/"


def stock(variant, qty):
    batch = Batch.objects.create(batch_code=f"G2-{variant.sku}-{Batch.objects.count()}", variant=variant,
                                 manufactured_on=timezone.localdate(), best_before=None,
                                 quantity_produced=qty, cost_per_unit_paise=0)
    receive_production(variant, batch, qty)


@pytest.fixture
def candle(vendor, config_settings):
    """One scent in three sizes: 100 g (default, 20 in stock), 200 g (3 in stock), 300 g (sold out)."""
    product = Product.objects.create(title="Test Scent", price=Decimal("499.00"), old_price=Decimal("599.00"),
                                     stock_qty=0, status="published", vendor=vendor)
    small = ProductVariant.objects.get(product=product, is_default=True)
    small.name, small.options, small.sku = "100 g", {"Size": "100 g"}, "T-100"
    small.save()
    medium = ProductVariant.objects.create(product=product, sku="T-200", name="200 g", options={"Size": "200 g"},
                                           price_paise=79900, mrp_paise=94900)
    large = ProductVariant.objects.create(product=product, sku="T-300", name="300 g", options={"Size": "300 g"},
                                          price_paise=119900, mrp_paise=139900)
    stock(small, 20)
    stock(medium, 3)
    return {"product": product, "small": small, "medium": medium, "large": large}


def set_history(variant, rows):
    """Replace a variant's recorded history with (days_ago, price_paise) rows, oldest first."""
    from django.db import connection

    with connection.cursor() as cursor:  # append-only in application code; a fixture may reset it
        cursor.execute("DELETE FROM catalog_pricehistory WHERE variant_id = %s", [variant.pk])
    now = timezone.now()
    for days_ago, price in rows:
        PriceHistory.objects.create(variant=variant, price_paise=price, mrp_paise=variant.mrp_paise,
                                    effective_from=now - timedelta(days=days_ago), actor_label="test")
    ProductVariant.objects.filter(pk=variant.pk).update(price_paise=rows[-1][1])
    variant.refresh_from_db()


# ------------------------------------------------------------------ price history

@pytest.mark.django_db
def test_a_new_variant_gets_an_opening_history_row(candle):
    rows = PriceHistory.objects.filter(variant=candle["medium"])
    assert rows.count() == 1
    assert (rows.get().price_paise, rows.get().mrp_paise) == (79900, 94900)


@pytest.mark.django_db
def test_every_price_change_writes_exactly_one_row_with_the_actor_from_any_entry_point(auth, staff, vendor, candle):
    small = candle["small"]
    product = candle["product"]
    history = PriceHistory.objects.filter(variant=small)
    baseline = history.count()

    # 1. Owner dashboard (API, JWT user).
    response = auth(staff).patch(f"{API}vendor-product-edit/{vendor.id}/{product.pid}/", {"price": "525.00"},
                                 format="multipart")
    assert response.status_code == 200
    assert history.count() == baseline + 1
    row = history.order_by("-id").first()
    assert (row.price_paise, row.actor_id, row.actor_label) == (52500, staff.id, f"user:{staff.id}")

    # 2. Django admin / any code acting as a user.
    with acting_as(staff):
        small.refresh_from_db()
        small.mrp_paise = 65000
        small.save()
    assert history.count() == baseline + 2
    assert history.order_by("-id").first().mrp_paise == 65000

    # 3. Shell or management command: no user, still recorded.
    small.price_paise = 51000
    small.save()
    assert history.count() == baseline + 3
    last = history.order_by("-id").first()
    assert (last.price_paise, last.actor, last.actor_label) == (51000, None, "system")

    # Saves that do not change the price write nothing.
    small.name = "100 g jar"
    small.save()
    small.save(update_fields=["name"])
    product.title = "Renamed Scent"
    product.save()
    assert history.count() == baseline + 3


@pytest.mark.django_db
def test_price_history_rows_cannot_be_updated_or_deleted(candle):
    row = PriceHistory.objects.filter(variant=candle["small"]).first()
    row.price_paise = 1
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        PriceHistory.objects.filter(pk=row.pk).update(price_paise=1)
    with pytest.raises(AppendOnlyError):
        PriceHistory.objects.all().delete()


# ------------------------------------------------------------------ strike-through

@pytest.mark.django_db
def test_flag_off_strikes_the_mrp_whenever_it_is_above_the_price(candle, settings):
    settings.STRIKETHROUGH_REQUIRES_PRICE_HISTORY = False
    assert strikethrough_for(candle["medium"]) == {"compare_at_paise": 94900, "percent_off": 15, "basis": "mrp"}

    medium = candle["medium"]
    for mrp in (None, 79900, 70000):  # no MRP, MRP equal to price, MRP below price: no claim
        medium.mrp_paise = mrp
        medium.save()
        assert strikethrough_for(medium) is None


@pytest.mark.django_db
def test_percent_off_is_rounded_down_never_up(candle, settings):
    settings.STRIKETHROUGH_REQUIRES_PRICE_HISTORY = False
    medium = candle["medium"]
    medium.price_paise, medium.mrp_paise = 66700, 100000  # 33.3% off
    medium.save()
    assert strikethrough_for(medium)["percent_off"] == 33
    medium.price_paise = 66001  # 33.999% off
    medium.save()
    assert strikethrough_for(medium)["percent_off"] == 33


@pytest.mark.django_db
def test_flag_on_requires_a_higher_price_on_record_in_the_window(candle, settings):
    settings.STRIKETHROUGH_REQUIRES_PRICE_HISTORY = True
    settings.PRICE_HISTORY_WINDOW_DAYS = 30
    medium = candle["medium"]  # MRP 949 is above the price, but MRP alone is not evidence here

    # Only ever one price: nothing to strike, whatever the MRP says.
    set_history(medium, [(10, 79900)])
    assert strikethrough_for(medium) is None

    # Lowered 2 days ago from 899: strike 899.
    set_history(medium, [(40, 89900), (2, 79900)])
    assert lowest_prior_price(medium) == 89900
    assert strikethrough_for(medium) == {"compare_at_paise": 89900, "percent_off": 11, "basis": "price_history"}

    # The LOWEST price in the window is the reference, not the highest.
    set_history(medium, [(40, 99900), (20, 84900), (2, 79900)])
    assert strikethrough_for(medium)["compare_at_paise"] == 84900

    # A brief spike just before the "sale" cannot manufacture a discount: 799 was charged
    # inside the window, so there is no reduction to claim.
    set_history(medium, [(40, 79900), (3, 99900), (2, 79900)])
    assert strikethrough_for(medium) is None

    # Raised price: no claim.
    set_history(medium, [(40, 69900), (2, 79900)])
    assert strikethrough_for(medium) is None

    # A price that stopped applying before the window opened does not count...
    set_history(medium, [(90, 149900), (60, 89900), (2, 79900)])
    assert strikethrough_for(medium)["compare_at_paise"] == 89900  # ...only the one in force during it


@pytest.mark.django_db
def test_an_mrp_only_edit_does_not_restart_the_current_price_period(candle, settings):
    settings.STRIKETHROUGH_REQUIRES_PRICE_HISTORY = True
    medium = candle["medium"]
    set_history(medium, [(40, 89900), (10, 79900)])
    medium.mrp_paise = 99900  # writes a history row with the same selling price
    medium.save()
    assert strikethrough_for(medium)["compare_at_paise"] == 89900


# ------------------------------------------------------------------ stock indicator

@pytest.mark.django_db
def test_stock_indicator_matches_the_ledger_and_never_invents_scarcity(candle, settings):
    settings.LOW_STOCK_THRESHOLD = 5
    small, medium, large = candle["small"], candle["medium"], candle["large"]

    assert stock_status(small) == {"state": IN_STOCK, "label": "In stock", "left": None}  # 20: no count shown
    assert stock_status(medium) == {"state": LOW_STOCK, "label": "Only 3 left", "left": 3}
    assert stock_status(medium)["left"] == available_qty(medium)
    assert stock_status(large) == {"state": SOLD_OUT, "label": "Sold out", "left": 0}

    reserve(small, 15, cart_id="someone-elses-cart")  # 5 left: exactly at the threshold
    assert stock_status(small) == {"state": LOW_STOCK, "label": "Only 5 left", "left": 5}
    settings.LOW_STOCK_THRESHOLD = 4  # 5 is now above the threshold
    assert stock_status(small) == {"state": IN_STOCK, "label": "In stock", "left": None}


# ------------------------------------------------------------------ API and cart

@pytest.mark.django_db
def test_product_api_exposes_options_price_stock_and_strikethrough_per_variant(api, candle):
    inactive = ProductVariant.objects.create(product=candle["product"], sku="T-OLD", name="Old size",
                                             options={"Size": "50 g"}, price_paise=10000, active=False)
    body = api.get(f"{API}products/{candle['product'].slug}/").json()

    by_sku = {v["sku"]: v for v in body["variants"]}
    assert set(by_sku) == {"T-100", "T-200", "T-300"} and inactive.sku not in by_sku
    assert body["variants"][0]["is_default"] is True
    assert by_sku["T-200"]["options"] == {"Size": "200 g"}
    assert by_sku["T-200"]["price_paise"] == 79900
    assert by_sku["T-200"]["strikethrough"] == {"compare_at_paise": 94900, "percent_off": 15, "basis": "mrp"}
    assert by_sku["T-200"]["stock"] == {"state": "low_stock", "label": "Only 3 left", "left": 3}
    assert by_sku["T-300"]["stock"]["state"] == "sold_out"
    assert body["available_qty"] == 23
    assert body["price_from_paise"] == 49900


@pytest.mark.django_db
def test_choosing_200g_adds_the_200g_variant_at_the_200g_price(api, candle):
    medium = candle["medium"]
    response = api.post(f"{API}cart-view/", {"product": candle["product"].id, "variant": medium.id, "qty": 1,
                                             "user": "undefined", "cart_id": "g2-cart-1"})
    assert response.status_code == 201
    line = Cart.objects.get(cart_id="g2-cart-1")
    assert (line.variant_id, line.price_paise, line.size) == (medium.id, 79900, "200 g")
    totals = api.get(f"{API}cart-detail/g2-cart-1/").json()
    assert totals["lines"][0]["variant_id"] == medium.id
    assert totals["subtotal_paise"] == 79900
    assert totals["amount_to_free_shipping_paise"] == 20000  # "Add Rs 200 more for free shipping"


@pytest.mark.django_db
def test_a_sold_out_variant_cannot_be_added_but_other_sizes_still_can(api, candle):
    payload = {"product": candle["product"].id, "qty": 1, "user": "undefined", "cart_id": "g2-cart-2"}
    sold_out = api.post(f"{API}cart-view/", {**payload, "variant": candle["large"].id})
    assert sold_out.status_code == 400
    assert Cart.objects.filter(cart_id="g2-cart-2").count() == 0

    assert api.post(f"{API}cart-view/", {**payload, "variant": candle["small"].id}).status_code == 201
    assert api.post(f"{API}cart-view/", {**payload, "variant": candle["medium"].id}).status_code == 201
    assert Cart.objects.filter(cart_id="g2-cart-2").count() == 2


# ------------------------------------------------------------------ stock_qty is read-only

@pytest.mark.django_db
def test_stock_qty_cannot_be_edited_from_the_dashboard_and_the_api_reports_the_ledger(auth, staff, vendor, candle):
    product = candle["product"]
    response = auth(staff).patch(f"{API}vendor-product-edit/{vendor.id}/{product.pid}/",
                                 {"stock_qty": "9999", "title": "Still The Same Stock"}, format="multipart")
    assert response.status_code == 200
    product.refresh_from_db()
    assert product.title == "Still The Same Stock"
    assert product.stock_qty == 0  # unchanged

    listing = auth(staff).get(f"{API}vendor/products/{vendor.id}/").json()
    row = next(p for p in listing if p["id"] == product.id)
    assert row["available_qty"] == 23


@pytest.mark.django_db
def test_stock_qty_is_read_only_in_django_admin(candle):
    admin = ProductAdmin(Product, AdminSite())
    assert "stock_qty" in admin.readonly_fields
    assert "stock_qty" not in admin.list_editable
    assert admin.available_now(candle["product"]) == 23


@pytest.mark.django_db
def test_adding_a_batch_in_admin_receives_its_stock_into_the_ledger(candle, staff):
    large = candle["large"]
    assert available_qty(large) == 0
    batch = Batch(batch_code="ADMIN-1", variant=large, manufactured_on=timezone.localdate(),
                  quantity_produced=12, cost_per_unit_paise=15000)
    request = RequestFactory().post("/admin/inventory/batch/add/")
    request.user = staff
    admin = BatchAdmin(Batch, AdminSite())

    admin.save_model(request, batch, form=None, change=False)
    assert available_qty(large) == 12
    assert batch.movements.get().actor_id == staff.id

    batch.production_notes = "edited"
    admin.save_model(request, batch, form=None, change=True)  # editing never re-books stock
    assert available_qty(large) == 12
    assert set(admin.get_readonly_fields(request, batch)) == {"variant", "quantity_produced"}


# ------------------------------------------------------------------ seed command

@pytest.mark.django_db
def test_seed_noore_refuses_to_run_outside_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_noore")
    assert Product.objects.count() == 0


@pytest.mark.django_db
def test_seed_noore_creates_the_placeholder_catalogue_and_is_idempotent(settings, api):
    settings.DEBUG = True
    call_command("seed_noore")
    call_command("seed_noore")

    assert Product.objects.count() == 3
    assert ProductVariant.objects.count() == 9
    assert Coupon.objects.filter(code="WELCOME10").count() == 1
    for product in Product.objects.all():
        variants = list(product.variants.order_by("price_paise"))
        assert [(v.name, v.price_paise, v.mrp_paise, v.weight_grams) for v in variants] == [
            ("100 g", 49900, 59900, 100), ("200 g", 79900, 94900, 200), ("300 g", 119900, 139900, 300)]
        assert [v.options for v in variants] == [{"Size": "100 g"}, {"Size": "200 g"}, {"Size": "300 g"}]
        assert [v.is_default for v in variants] == [True, False, False]
        assert all(not v.perishable for v in variants)
        assert all(available_qty(v) == 20 for v in variants)
        assert product.price == Decimal("499.00")
    assert Batch.objects.count() == 9

    body = api.get(f"{API}products/noore-lavender/").json()
    assert len(body["variants"]) == 3 and body["available_qty"] == 60


# ------------------------------------------------------------------ deleting and hiding products

@pytest.mark.django_db
def test_a_product_with_no_history_can_be_deleted(auth, staff, vendor, config_settings):
    fresh = Product.objects.create(title="Never Sold", price=Decimal("10.00"), stock_qty=0,
                                   status="published", vendor=vendor)
    response = auth(staff).delete(f"{API}vendor-product-delete/{vendor.id}/{fresh.pid}/")
    assert response.status_code == 204
    assert not Product.objects.filter(pk=fresh.pk).exists()
    assert AuditLog.objects.filter(action="product.deleted", object_id=str(fresh.pk)).exists()


@pytest.mark.django_db
def test_a_product_with_stock_or_orders_is_refused_with_an_explanation_not_a_server_error(auth, staff, vendor, candle, make_order):
    product = candle["product"]
    owner = auth(staff)

    # Stock history alone is enough to refuse.
    refused = owner.delete(f"{API}vendor-product-delete/{vendor.id}/{product.pid}/")
    assert refused.status_code == 409
    body = refused.json()
    assert "stock history" in body["message"] and product.title in body["message"]
    assert body["can_hide"] is True
    assert Product.objects.filter(pk=product.pk).exists()
    assert ProductVariant.objects.filter(product=product).count() == 3

    # And so is having been ordered.
    order = make_order(payment_status="paid")
    CartOrderItem.objects.create(order=order, product=product, variant=candle["small"], qty=1,
                                 price=Decimal("499.00"), sub_total=Decimal("499.00"), total=Decimal("499.00"))
    ordered = owner.delete(f"{API}vendor-product-delete/{vendor.id}/{product.pid}/")
    assert ordered.status_code == 409
    assert "ordered" in ordered.json()["message"]


@pytest.mark.django_db
def test_hiding_a_product_removes_it_from_the_shop_and_showing_it_brings_it_back(api, auth, staff, vendor, candle):
    product = candle["product"]
    owner = auth(staff)
    url = f"{API}vendor-product-visibility/{vendor.id}/{product.pid}/"

    def in_shop():
        return any(row["id"] == product.id for row in api.get(f"{API}products/").json())

    assert in_shop()

    hidden = owner.post(url, {"status": "disabled"})
    assert hidden.status_code == 200 and hidden.json()["status"] == "disabled"
    assert not in_shop()
    assert api.get(f"{API}products/{product.slug}/").status_code == 404
    # Nothing was lost: its stock, variants and history are all still there.
    product.refresh_from_db()
    assert ProductVariant.objects.filter(product=product).count() == 3
    assert available_qty(candle["small"]) == 20

    back = owner.post(url, {"status": "published"})
    assert back.status_code == 200 and in_shop()

    assert [(a.before["status"], a.after["status"]) for a in
            AuditLog.objects.filter(action="product.status", object_id=str(product.pk)).order_by("id")] == [
        ("published", "disabled"), ("disabled", "published")]

    assert owner.post(url, {"status": "nonsense"}).status_code == 400


@pytest.mark.django_db
def test_deleting_and_hiding_are_staff_only(api, auth, customer, vendor, candle):
    product = candle["product"]
    for client in (api, auth(customer)):
        assert client.delete(f"{API}vendor-product-delete/{vendor.id}/{product.pid}/").status_code in (401, 403)
        assert client.post(f"{API}vendor-product-visibility/{vendor.id}/{product.pid}/", {"status": "disabled"}).status_code in (401, 403)
    product.refresh_from_db()
    assert product.status == "published"


# ------------------------------------------------------------------ purging demo products

@pytest.mark.django_db
def test_purge_product_erases_a_demo_product_and_its_ledger_rows(candle, capsys):
    """The dashboard refuses; the command exists for exactly this, and records what it removed."""
    from django.core.management import call_command

    from catalog.models import PriceHistory
    from core.models import AuditLog
    from inventory.models import StockMovement

    product = candle["product"]
    Product.objects.filter(pk=product.pk).update(slug="hoodie-t-shirt-for-men")
    variant_ids = list(product.variants.values_list("id", flat=True))
    assert StockMovement.objects.filter(variant_id__in=variant_ids).exists()

    keeper = Product.objects.create(title="Real Candle", price=Decimal("499.00"), stock_qty=3,
                                    status="published", vendor=product.vendor)

    call_command("purge_product", "--demo", "--force")

    assert not Product.objects.filter(pk=product.pk).exists()
    assert ProductVariant.objects.filter(product_id=product.pk).count() == 0
    assert StockMovement.objects.filter(variant_id__in=variant_ids).count() == 0
    assert Batch.objects.filter(variant_id__in=variant_ids).count() == 0
    assert PriceHistory.objects.filter(variant_id__in=variant_ids).count() == 0
    # Everything else is untouched, and the audit log says what went.
    assert Product.objects.filter(pk=keeper.pk).exists()
    assert available_qty(ProductVariant.objects.get(product=keeper, is_default=True)) == 3
    purged = AuditLog.objects.get(action="product.purged")
    assert purged.before["sku"] == product.sku and purged.before["movements"] >= 1


@pytest.mark.django_db
def test_purge_product_refuses_to_erase_anything_that_has_been_ordered(candle, make_order):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    product = candle["product"]
    CartOrderItem.objects.create(order=make_order(), product=product, variant=candle["small"], qty=1,
                                 price=Decimal("499.00"), sub_total=Decimal("499.00"), total=Decimal("499.00"))

    with pytest.raises(CommandError) as refused:
        call_command("purge_product", "--slug", product.slug, "--force")
    assert "order" in str(refused.value) and "Hide it" in str(refused.value)
    assert Product.objects.filter(pk=product.pk).exists()
    assert available_qty(candle["small"]) == 20


# ------------------------------------------------------------------ adding a product

def product_form(vendor, **overrides):
    """What the dashboard's "Add Product" form submits, including its blank repeatable rows."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    payload = {
        "title": "Rose Candle", "image": SimpleUploadedFile("rose.jpg", b"\xff\xd8\xffdata", content_type="image/jpeg"),
        "description": "<p>Hand poured.</p>", "category": "", "tags": "candle", "brand": "",
        "price": "499.00", "old_price": "599.00", "shipping_amount": "0", "stock_qty": "5", "vendor": vendor.id,
        # The form always sends one empty row per repeatable section until the owner fills it in.
        "specifications[0][title]": "", "specifications[0][content]": "",
        "colors[0][name]": "", "colors[0][color_code]": "", "colors[0][image]": "null",
        "sizes[0][name]": "", "sizes[0][price]": "",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_adding_a_product_with_untouched_optional_sections_works(auth, staff, vendor, config_settings):
    response = auth(staff).post(f"{API}vendor-product-create/{vendor.id}/", product_form(vendor), format="multipart")
    assert response.status_code == 201, response.content

    product = Product.objects.get(title="Rose Candle")
    assert product.specification_set.count() == 0 and product.size_set.count() == 0 and product.color_set.count() == 0
    # It is sellable straight away: a default variant at the price typed, with the opening stock.
    variant = ProductVariant.objects.get(product=product, is_default=True)
    assert (variant.price_paise, variant.mrp_paise) == (49900, 59900)
    assert available_qty(variant) == 5


@pytest.mark.django_db
def test_filled_in_sections_are_still_saved(auth, staff, vendor, config_settings):
    response = auth(staff).post(f"{API}vendor-product-create/{vendor.id}/", product_form(
        vendor,
        **{"specifications[0][title]": "Burn time", "specifications[0][content]": "40 hours",
           "sizes[0][name]": "200 g", "sizes[0][price]": "799"}), format="multipart")
    assert response.status_code == 201, response.content

    product = Product.objects.get(title="Rose Candle")
    assert [(s.title, s.content) for s in product.specification_set.all()] == [("Burn time", "40 hours")]
    assert [(s.name, str(s.price)) for s in product.size_set.all()] == [("200 g", "799.00")]


@pytest.mark.django_db
def test_placeholder_text_for_an_empty_file_does_not_count_as_a_filled_in_row(auth, staff, vendor, config_settings):
    """A browser form can send the word "null" where a file would go; that is still an empty row."""
    for index, placeholder in enumerate(("null", "undefined", "None", "  ")):
        title = f"Rose Candle {index}"
        response = auth(staff).post(f"{API}vendor-product-create/{vendor.id}/", product_form(
            vendor, title=title, **{"colors[0][image]": placeholder, "gallery[0][image]": placeholder}),
            format="multipart")
        assert response.status_code == 201, (placeholder, response.content)
        product = Product.objects.get(title=title)
        assert product.color_set.count() == 0 and product.gallery_set.count() == 0


@pytest.mark.django_db
def test_a_half_filled_section_still_reports_its_own_error(auth, staff, vendor, config_settings):
    """A row the owner did start must not be silently dropped: the server says what is missing."""
    response = auth(staff).post(f"{API}vendor-product-create/{vendor.id}/", product_form(
        vendor, **{"sizes[0][name]": "200 g", "sizes[0][price]": ""}), format="multipart")
    assert response.status_code == 400
    assert "price" in response.content.decode()
    assert not Product.objects.filter(title="Rose Candle").exists()  # nothing half-saved