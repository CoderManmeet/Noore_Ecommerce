"""
Regression tests for editing a product from the owner dashboard.

The edit screen loads a product and posts every field back, so image fields arrive as the URL
strings the API served. Before this fix that produced:
    400 {"image": ["The submitted data was not a file. Check the encoding type on the form."]}
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from store.models import Color, Gallery, Size, Specification


def form_from_api(payload, **overrides):
    """Turn a GET response into the multipart body the edit screen actually sends."""
    form = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            form[key] = "[object Object]"
        elif isinstance(value, list):
            continue
        elif value is None:
            continue
        elif isinstance(value, bool):
            form[key] = "true" if value else "false"
        else:
            form[key] = str(value)
    form.update(overrides)
    return form


def png_bytes():
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
            b"\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def edit_url(vendor, product):
    return f"/api/v1/vendor-product-edit/{vendor.id}/{product.pid}/"


@pytest.mark.django_db
def test_price_edit_succeeds_when_image_is_echoed_back_as_a_url(auth, staff, product, edit_url):
    client = auth(staff)
    payload = client.get(edit_url).json()
    assert str(payload["image"]).startswith("http")

    response = client.patch(edit_url, form_from_api(payload, price="60"), format="multipart")

    assert response.status_code == 200, response.json()
    product.refresh_from_db()
    assert str(product.price) == "60.00"


@pytest.mark.django_db
def test_price_edit_keeps_the_existing_product_image(auth, staff, product, edit_url):
    product.image.save("existing.png", SimpleUploadedFile("existing.png", png_bytes()), save=True)
    original_image = product.image.name

    client = auth(staff)
    payload = client.get(edit_url).json()
    assert client.patch(edit_url, form_from_api(payload, price="75"), format="multipart").status_code == 200

    product.refresh_from_db()
    assert product.image.name == original_image
    assert str(product.price) == "75.00"


@pytest.mark.django_db
def test_price_edit_does_not_wipe_gallery_colors_sizes_or_specifications(auth, staff, product, edit_url):
    gallery_row = Gallery.objects.create(product=product)
    gallery_row.image.save("gallery.png", SimpleUploadedFile("gallery.png", png_bytes()), save=True)
    color_row = Color.objects.create(product=product, name="Red", color_code="#ff0000")
    color_row.image.save("color.png", SimpleUploadedFile("color.png", png_bytes()), save=True)
    stored_color_image = color_row.image.name
    Size.objects.create(product=product, name="M", price="10.00")
    Specification.objects.create(product=product, title="Fabric", content="Cotton")

    client = auth(staff)
    payload = client.get(edit_url).json()
    body = form_from_api(payload, price="61")
    # Exactly what the screen sends back for existing nested rows.
    body["specifications[0][title]"] = "Fabric"
    body["specifications[0][content]"] = "Cotton"
    body["colors[0][name]"] = "Red"
    body["colors[0][color_code]"] = "#ff0000"
    body["colors[0][image]"] = f"http://127.0.0.1:8000/media/{stored_color_image}"
    body["sizes[0][name]"] = "M"
    body["sizes[0][price]"] = "10.00"
    body["gallery[0][image]"] = "undefined"  # the screen's own placeholder for an unchanged image

    assert client.patch(edit_url, body, format="multipart").status_code == 200

    product.refresh_from_db()
    assert str(product.price) == "61.00"
    assert Gallery.objects.filter(product=product).count() == 1
    assert Size.objects.filter(product=product).count() == 1
    assert Specification.objects.filter(product=product).count() == 1
    colors = Color.objects.filter(product=product)
    assert colors.count() == 1
    assert colors.get().image.name == stored_color_image


@pytest.mark.django_db
def test_a_new_image_upload_still_replaces_the_product_image(auth, staff, product, edit_url):
    client = auth(staff)
    payload = client.get(edit_url).json()
    body = form_from_api(payload, price="80")
    body["image"] = SimpleUploadedFile("new.png", png_bytes(), content_type="image/png")

    assert client.patch(edit_url, body, format="multipart").status_code == 200

    product.refresh_from_db()
    # user_directory_path renames uploads to <user id>.<ext>, so assert on the extension.
    assert product.image.name.endswith(".png")
    assert product.image.read() == png_bytes()
    assert str(product.price) == "80.00"


@pytest.mark.django_db
def test_category_can_be_changed_by_id_and_is_untouched_when_echoed_back(auth, staff, product, edit_url):
    from store.models import Category

    first = Category.objects.create(title="Cloths")
    second = Category.objects.create(title="Bags")
    product.category = first
    product.save()

    client = auth(staff)
    payload = client.get(edit_url).json()

    # Unchanged: the whole category object comes back as "[object Object]" and must be ignored.
    assert client.patch(edit_url, form_from_api(payload, price="62"), format="multipart").status_code == 200
    product.refresh_from_db()
    assert product.category_id == first.id

    # Changed: the form sends the new category id.
    assert client.patch(edit_url, form_from_api(payload, category=str(second.id)), format="multipart").status_code == 200
    product.refresh_from_db()
    assert product.category_id == second.id


@pytest.mark.django_db
def test_product_edit_is_still_staff_only(api, auth, customer, product, edit_url):
    assert api.patch(edit_url, {"price": "1"}, format="multipart").status_code == 401
    assert auth(customer).patch(edit_url, {"price": "1"}, format="multipart").status_code == 403
    product.refresh_from_db()
    assert str(product.price) == "56.00"


@pytest.mark.django_db
def test_a_traversal_path_in_an_image_field_is_rejected(auth, staff, product, edit_url):
    client = auth(staff)
    payload = client.get(edit_url).json()
    body = form_from_api(payload, price="63")
    body["gallery[0][image]"] = "http://127.0.0.1:8000/media/../../etc/passwd"

    assert client.patch(edit_url, body, format="multipart").status_code == 200
    assert Gallery.objects.filter(product=product).count() == 0

