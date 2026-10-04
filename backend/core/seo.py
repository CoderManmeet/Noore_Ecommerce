"""
Search-engine and link-preview basics (Phase G5): robots.txt, sitemap.xml, and product pages
whose <head> carries the product's own title, description, price and image.

The storefront is a single-page app: every URL serves the same index.html, so a link shared on
WhatsApp or social media would otherwise preview as a blank generic page. In production the
web server sends product URLs (/detail/<slug>) here; this view returns the built index.html
with the product's tags filled in. The page then starts the React app exactly as usual.
"""

import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.html import escape, strip_tags
from django.views.decorators.http import require_GET

from core.money import from_paise

# Storefront pages that exist for every shopper (products are added from the database).
STATIC_PATHS = ("/", "/policy/shipping", "/policy/returns", "/policy/privacy", "/policy/terms", "/contact")

# Nothing here is for search engines: accounts, carts, checkout, the dashboard and the API.
DISALLOWED = ("/admin/", "/api/", "/cart/", "/checkout/", "/order/", "/customer/", "/vendor/", "/owner/",
              "/claim-account", "/login", "/register", "/search")

TITLE_TAG = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
_index_cache = {"path": None, "mtime": None, "html": None}


@require_GET
def robots_txt(request):
    lines = ["User-agent: *"] + [f"Disallow: {path}" for path in DISALLOWED]
    lines += ["", f"Sitemap: {settings.SITE_URL}/sitemap.xml", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request):
    from store.models import Product

    urls = [f"{settings.SITE_URL}{path}" for path in STATIC_PATHS]
    for slug in Product.objects.filter(status="published").exclude(slug__isnull=True).exclude(slug="") \
            .order_by("id").values_list("slug", flat=True):
        urls.append(f"{settings.SITE_URL}/detail/{slug}")
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    body += [f"  <url><loc>{escape(url)}</loc></url>" for url in urls]
    body.append("</urlset>")
    return HttpResponse("\n".join(body) + "\n", content_type="application/xml; charset=utf-8")


def _index_html():
    """The built index.html, re-read only when the file changes (i.e. after a deploy)."""
    if not settings.FRONTEND_INDEX_PATH:
        return None
    path = Path(settings.FRONTEND_INDEX_PATH)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _index_cache["path"] != str(path) or _index_cache["mtime"] != mtime:
        _index_cache.update(path=str(path), mtime=mtime, html=path.read_text(encoding="utf-8"))
    return _index_cache["html"]


def product_head_tags(product, request):
    """The <title> and meta tags for one product. Every value is HTML-escaped."""
    variants = list(product.variants.filter(active=True).order_by("-is_default", "price_paise", "id"))
    title = f"{product.title} | {settings.STORE_NAME}"
    description = " ".join(strip_tags(product.description or "").split())[:200] or f"{product.title} from {settings.STORE_NAME}."
    url = f"{settings.SITE_URL}/detail/{product.slug}"
    tags = [
        f"<title>{escape(title)}</title>",
        f'<meta name="description" content="{escape(description)}" />',
        f'<link rel="canonical" href="{escape(url)}" />',
        '<meta property="og:type" content="product" />',
        f'<meta property="og:site_name" content="{escape(settings.STORE_NAME)}" />',
        f'<meta property="og:title" content="{escape(product.title)}" />',
        f'<meta property="og:description" content="{escape(description)}" />',
        f'<meta property="og:url" content="{escape(url)}" />',
    ]
    if product.image:
        try:
            image_url = request.build_absolute_uri(product.image.url)
            tags.append(f'<meta property="og:image" content="{escape(image_url)}" />')
        except ValueError:
            pass
    if variants:
        lowest = min(variant.price_paise for variant in variants)
        tags.append(f'<meta property="product:price:amount" content="{from_paise(int(lowest))}" />')
        tags.append('<meta property="product:price:currency" content="INR" />')
    return tags


@require_GET
def product_page(request, slug):
    from store.models import Product

    html = _index_html()
    if html is None:
        # Not configured (development): the dev server or the web server serves the app itself.
        raise Http404("The storefront page is served by the frontend.")
    product = Product.objects.filter(slug=slug, status="published").first()
    if product is None:
        # Unknown product: the unchanged app page, which shows its own not-found state.
        return HttpResponse(html, content_type="text/html; charset=utf-8")

    tags = product_head_tags(product, request)
    title_tag, other_tags = tags[0], "\n    ".join(tags[1:])
    # Lambdas: the replacement text must be inserted literally, never read as a regex template.
    if TITLE_TAG.search(html):
        page = TITLE_TAG.sub(lambda _match: title_tag, html, count=1)
    else:
        page = re.sub(r"</head>", lambda _match: f"{title_tag}\n</head>", html, count=1, flags=re.IGNORECASE)
    page = re.sub(r"</head>", lambda _match: f"    {other_tags}\n  </head>", page, count=1, flags=re.IGNORECASE)
    return HttpResponse(page, content_type="text/html; charset=utf-8")
