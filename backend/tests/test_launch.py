"""
Phase G5 (part A, launch preparation) tests: production settings, the shared cache for rate
limits, error-report emails, the health check, robots.txt, sitemap.xml and product link previews.

Every test here fails before this phase (the settings, core.health, core.seo and
core.error_email did not exist) and passes after it.
"""

import logging
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.core.cache import caches
from django.core.management import call_command
from django.utils import timezone

from core.models import Job
from store.models import Product

API = "/api/v1/"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def production_settings(*names, **extra_env):
    """Load backend.settings in a fresh process with DEBUG off and print the named settings."""
    code = "import json; from django.conf import settings; import django; django.setup(); " \
           f"print(json.dumps({{n: getattr(settings, n, None) for n in {list(names)!r}}}, default=str))"
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings", "DJANGO_DEBUG": "False", **extra_env}
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
    import json

    return json.loads(result.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------------- production settings

def test_production_settings_are_secure_by_default():
    values = production_settings(
        "DEBUG", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS",
        "SECURE_PROXY_SSL_HEADER", "SECURE_CONTENT_TYPE_NOSNIFF", "X_FRAME_OPTIONS", "SECURE_REDIRECT_EXEMPT",
        "DJANGO_CACHE", "CACHES",
    )
    assert values["DEBUG"] is False
    assert values["SESSION_COOKIE_SECURE"] is True and values["CSRF_COOKIE_SECURE"] is True
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SECURE_HSTS_SECONDS"] >= 3600
    assert values["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert values["SECURE_CONTENT_TYPE_NOSNIFF"] is True and values["X_FRAME_OPTIONS"] == "DENY"
    assert values["SECURE_REDIRECT_EXEMPT"] == ["^api/v1/health/$"]
    # Rate limits are shared between processes in production (bug D14).
    assert values["DJANGO_CACHE"] == "db"
    assert values["CACHES"]["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"


def test_django_deployment_check_passes_with_production_settings():
    env = {**os.environ, "DJANGO_DEBUG": "False", "SECURE_HSTS_SECONDS": "31536000",
           "SECURE_HSTS_INCLUDE_SUBDOMAINS": "True", "SECURE_HSTS_PRELOAD": "True",
           "DJANGO_SECRET_KEY": "x" * 60 + "Aa1!-not-a-real-key-only-for-this-check"}
    result = subprocess.run([sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
                            cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def test_development_keeps_the_per_process_cache(settings):
    assert settings.DEBUG is True or settings.DJANGO_CACHE in ("locmem", "db")
    assert production_settings("DJANGO_CACHE", DJANGO_DEBUG="True")["DJANGO_CACHE"] == "locmem"


# --------------------------------------------------------------------------- shared rate limits

@pytest.mark.django_db
def test_rate_limits_are_counted_in_the_shared_database_cache(api, settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "django_cache"}}
    call_command("createcachetable")
    caches["default"].clear()

    statuses = [api.get(f"{API}user/password-reset/nobody@example.com/").status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5 and statuses[5:] == [429, 429]  # "otp" scope: 5 a minute

    # The count lives in the database table, where every server process sees the same number.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM django_cache WHERE cache_key LIKE %s", ["%throttle_otp%"])
        assert cursor.fetchone()[0] == 1
    caches["default"].clear()


# --------------------------------------------------------------------------- error emails

@pytest.mark.django_db
def test_errors_are_emailed_masked_and_not_repeated(settings, mailoutbox):
    from core.error_email import ErrorEmailHandler
    from core.logmask import PIIMaskingFilter

    settings.ERROR_REPORT_EMAILS = ["owner@example.com"]
    settings.ERROR_REPORT_MIN_INTERVAL_SECONDS = 300
    logger = logging.getLogger("tests.error_email")
    handler = ErrorEmailHandler(level=logging.ERROR)
    handler.addFilter(PIIMaskingFilter())
    logger.addHandler(handler)
    try:
        for _ in range(3):
            try:
                raise ValueError("boom for asha@example.com on +919876543210")
            except ValueError:
                logger.exception("payment step failed for asha@example.com")
        logger.warning("a warning is not an error")
        logger.error("a different problem")
    finally:
        logger.removeHandler(handler)

    assert len(mailoutbox) == 2  # the repeated error once, the different one once
    first = mailoutbox[0]
    assert first.to == ["owner@example.com"]
    assert "payment step failed" in first.subject and "ValueError" in first.body
    assert "asha@example.com" not in first.body + first.subject
    assert "9876543210" not in first.body


@pytest.mark.django_db
def test_no_error_email_without_recipients_and_a_broken_mail_server_never_raises(settings, mailoutbox):
    from core.error_email import ErrorEmailHandler

    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failure %s", ("one",), None)
    settings.ERROR_REPORT_EMAILS = []
    ErrorEmailHandler().emit(record)
    assert mailoutbox == []

    settings.ERROR_REPORT_EMAILS = ["owner@example.com"]
    with mock.patch("django.core.mail.send_mail", side_effect=RuntimeError("smtp down")):
        ErrorEmailHandler().emit(record)  # must not raise


# --------------------------------------------------------------------------- health check

@pytest.mark.django_db
def test_health_check_reports_database_cache_and_worker(api, settings):
    settings.WORKER_STALE_AFTER_SECONDS = 300

    body = api.get(f"{API}health/")
    assert body.status_code == 200
    assert body.json() == {"status": "ok", "database": True, "cache": True,
                           "worker": {"ok": False, "seconds_since_last_job": None}}
    assert api.get(f"{API}health/?strict=1").status_code == 503  # the worker has never run

    Job.objects.create(name="x", status=Job.STATUS_DONE, finished_at=timezone.now() - timedelta(seconds=30))
    strict = api.get(f"{API}health/?strict=1")
    assert strict.status_code == 200 and strict.json()["worker"]["ok"] is True

    Job.objects.all().update(finished_at=timezone.now() - timedelta(minutes=20))
    assert api.get(f"{API}health/").status_code == 200           # the site itself is still up
    assert api.get(f"{API}health/?strict=1").status_code == 503  # but the worker has stopped

    with mock.patch("core.health._database_ok", return_value=False):
        down = api.get(f"{API}health/")
    assert down.status_code == 503 and down.json()["status"] == "down"


@pytest.mark.django_db
def test_health_check_is_never_rate_limited(api):
    assert {api.get(f"{API}health/").status_code for _ in range(400)} == {200}


# --------------------------------------------------------------------------- robots, sitemap, previews

@pytest.mark.django_db
def test_robots_txt_keeps_private_areas_out_and_points_to_the_sitemap(client, settings):
    settings.SITE_URL = "https://shop.test"
    response = client.get("/robots.txt")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/plain")
    text = response.content.decode()
    for private in ("/admin/", "/api/", "/cart/", "/checkout/", "/order/", "/customer/", "/owner/"):
        assert f"Disallow: {private}" in text
    assert "Disallow: /detail" not in text and "Disallow: /\n" not in text
    assert "Sitemap: https://shop.test/sitemap.xml" in text


@pytest.mark.django_db
def test_sitemap_lists_published_products_and_public_pages_only(client, settings, product, vendor):
    settings.SITE_URL = "https://shop.test"
    draft = Product.objects.create(title="Hidden Draft", price="10.00", status="draft", vendor=vendor)
    text = client.get("/sitemap.xml").content.decode()
    assert f"<loc>https://shop.test/detail/{product.slug}</loc>" in text
    assert draft.slug not in text
    for path in ("/", "/policy/shipping", "/policy/returns", "/policy/privacy", "/policy/terms", "/contact"):
        assert f"<loc>https://shop.test{path}</loc>" in text
    assert "/cart" not in text and "/admin" not in text


INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Store</title>
  </head>
  <body><div id="root"></div><script type="module" src="/assets/index.js"></script></body>
</html>
"""


@pytest.mark.django_db
def test_product_urls_get_their_own_title_description_price_and_image(client, settings, product, tmp_path):
    index = tmp_path / "index.html"
    index.write_text(INDEX, encoding="utf-8")
    settings.FRONTEND_INDEX_PATH = str(index)
    settings.SITE_URL = "https://shop.test"
    settings.STORE_NAME = "Noore Candles"
    Product.objects.filter(pk=product.pk).update(
        title='Rose & "Oud" <Candle>', description="<p>Hand-poured.</p>\n<script>alert(1)</script> Burns 40 hours \\1.")
    product.refresh_from_db()

    for url in (f"/detail/{product.slug}", f"/detail/{product.slug}/"):
        html = client.get(url).content.decode()
        assert "<title>Rose &amp; &quot;Oud&quot; &lt;Candle&gt; | Noore Candles</title>" in html
        assert html.count("<title>") == 1 and "<title>Store</title>" not in html
        assert '<meta property="og:title" content="Rose &amp; &quot;Oud&quot; &lt;Candle&gt;" />' in html
        assert 'content="Hand-poured. alert(1) Burns 40 hours \\1."' in html  # tags stripped, text escaped, literal
        assert "<script>alert(1)</script>" not in html
        assert f'<link rel="canonical" href="https://shop.test/detail/{product.slug}" />' in html
        assert '<meta property="product:price:amount" content="56.00" />' in html
        assert '<meta property="product:price:currency" content="INR" />' in html
        assert 'property="og:image" content="http://testserver/media/' in html
        assert '<div id="root"></div>' in html and 'src="/assets/index.js"' in html  # the app still boots


@pytest.mark.django_db
def test_unknown_or_unpublished_products_get_the_plain_app_page(client, settings, product, vendor, tmp_path):
    index = tmp_path / "index.html"
    index.write_text(INDEX, encoding="utf-8")
    settings.FRONTEND_INDEX_PATH = str(index)
    draft = Product.objects.create(title="Secret Draft", price="10.00", status="draft", vendor=vendor)

    for slug in ("no-such-product", draft.slug):
        response = client.get(f"/detail/{slug}")
        assert response.status_code == 200
        assert response.content.decode() == INDEX
    assert "Secret Draft" not in client.get(f"/detail/{draft.slug}").content.decode()

    settings.FRONTEND_INDEX_PATH = ""  # development: the dev server serves the page
    assert client.get(f"/detail/{product.slug}").status_code == 404


# --------------------------------------------------------------------------- G4.5: staff flag

@pytest.mark.django_db
def test_sign_in_token_says_whether_the_user_is_staff_and_the_api_does_not_trust_it(api, auth, staff, customer):
    """The storefront shows the "Admin" link from this claim; the API still checks the database."""
    import jwt

    def claims(user, password):
        response = api.post(f"{API}user/token/", {"email": user.email, "password": password})
        assert response.status_code == 200
        return jwt.decode(response.json()["access"], options={"verify_signature": False})

    customer.set_password("Str0ng!Passw0rd"); customer.save()
    staff.set_password("Str0ng!Passw0rd"); staff.save()
    assert claims(customer, "Str0ng!Passw0rd")["is_staff"] is False
    assert claims(staff, "Str0ng!Passw0rd")["is_staff"] is True

    # A customer cannot reach an owner endpoint whatever their browser claims.
    assert auth(customer).get(f"{API}owner/orders/").status_code == 403
    assert auth(staff).get(f"{API}owner/orders/").status_code == 200
