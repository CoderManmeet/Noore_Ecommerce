# Django Packages
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone

# Restframework Packages
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

# Serializers
from store.serializers import CartOrderSerializer, CartSerializer, CategorySerializer, BrandSerializer, ConfigSettingsSerializer, ProductSerializer, ReviewSerializer

# Models
from addon.models import ConfigSettings
from store.models import PAYMENT_METHOD_CHOICES, REVIEW_APPROVED, REVIEW_PENDING, Brand, Cart, CartOrder, CartOrderItem, Category, Coupon, Notification, Product, Review

# Platform
from core.idempotency import claim_event
from core.permissions import ensure_order_access, ensure_self_or_staff
from core.phone import try_to_e164
from catalog.models import ProductVariant
from inventory.models import ReservationStatus, StockReservation
from inventory.services import InsufficientStock, attach_reservations_to_order, reserve
from core.money import from_paise
from store.money_mirror import set_money
from store import payments
from store.order_state import mark_paid
from store.pricing import Customer, apply_quote_to_order, quote, record_redemption

# Others Packages
import requests
import stripe

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
PAYPAL_CLIENT_ID = settings.PAYPAL_CLIENT_ID
PAYPAL_SECRET_ID = settings.PAYPAL_SECRET_ID

EXTERNAL_TIMEOUT_SECONDS = 15


def send_notification(user=None, vendor=None, order=None, order_item=None):
    Notification.objects.create(
        user=user,
        vendor=vendor,
        order=order,
        order_item=order_item,
    )


def _optional_user_id(value):
    """Frontend sends user ids as numbers, numeric strings, 0, "undefined" or "null"."""
    if value in (None, "", 0, "0", "undefined", "null"):
        return None
    return value


def resolve_variant(product, size=None, color=None):
    """
    Find the sellable unit for a product line.

    The storefront still posts free-text size/colour, so match on those first and fall back
    to the product's default variant. Every product has a default variant after the F-B backfill.
    """
    variants = list(ProductVariant.objects.filter(product=product, active=True))
    if not variants:
        return None
    size = (size or "").strip()
    color = (color or "").strip()
    if size or color:
        for variant in variants:
            if (not size or variant.size == size) and (not color or variant.color == color):
                if variant.size or variant.color:
                    return variant
    for variant in variants:
        if variant.is_default:
            return variant
    return variants[0]


def default_variant_for(product):
    """The product's default (or first active) variant, or None."""
    return resolve_variant(product)


def variant_for_cart_line(cart_line):
    """The sellable unit a cart row refers to; legacy rows without one use the default variant."""
    if cart_line.variant_id:
        return cart_line.variant
    return default_variant_for(cart_line.product)


# Payment states in which an order is still a draft the customer may change.
DRAFT_PAYMENT_STATUSES = ("initiated", "processing")
# Payment states in which an order is finished with and its cart may start a new order.
DEAD_PAYMENT_STATUSES = ("cancelled", "expired")


def order_is_dead(order):
    return order.order_status == "Cancelled" or order.payment_status in DEAD_PAYMENT_STATUSES


class ConfigSettingsDetailView(generics.RetrieveAPIView):
    serializer_class = ConfigSettingsSerializer
    permission_classes = (AllowAny,)

    def get_object(self):
        return ConfigSettings.objects.first()


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(active=True)
    permission_classes = (AllowAny,)


class BrandListView(generics.ListAPIView):
    serializer_class = BrandSerializer
    queryset = Brand.objects.filter(active=True)
    permission_classes = (AllowAny,)


class CatalogueListMixin:
    """
    Serialises a page of products without asking the database once per product.

    Everything the cards need (variants, images, the shop) is fetched in a handful of queries,
    and the stock of every variant on the page is read in two more and handed to the
    serializers. Without this a page of eight products cost over two hundred round trips.
    """

    def get_queryset(self):
        from catalog.models import ProductVariant

        return (
            Product.objects.filter(status="published")
            .select_related("vendor", "vendor__user", "category")
            .annotate(
                _rating_avg=Avg("reviews__rating", filter=Q(reviews__status=REVIEW_APPROVED)),
                _rating_count=Count("reviews", filter=Q(reviews__status=REVIEW_APPROVED), distinct=True),
                _order_count=Count("order_item", filter=Q(order_item__order__payment_status="paid"), distinct=True),
            )
            .prefetch_related(
                Prefetch("variants", queryset=ProductVariant.objects.filter(active=True)
                         .order_by("-is_default", "price_paise", "id"), to_attr="_prefetched_active_variants"),
                "gallery_set", "specification_set", "size_set", "color_set",
            )
        )

    def get_serializer_context(self):
        from inventory.services import available_qty_map

        context = super().get_serializer_context()
        page = getattr(self, "_page_for_context", None)
        if page is not None:
            variants = [variant for product in page for variant in getattr(product, "_prefetched_active_variants", [])]
            context["available_qty_map"] = available_qty_map(variants)
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        self._page_for_context = rows
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class FeaturedProductListView(CatalogueListMixin, generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return super().get_queryset().filter(featured=True)[:3]


class ProductListView(CatalogueListMixin, generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)


class ProductDetailView(generics.RetrieveAPIView):
    """
    One product, for the storefront. Only a published product is visible: a draft or a product
    the owner has hidden is not shown at its address either, so hiding really hides it.
    Staff can still open an unpublished product to check it before publishing.
    """

    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_object(self):
        from catalog.models import ProductVariant

        queryset = Product.objects.select_related("vendor", "vendor__user", "category").prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.filter(active=True)
                     .order_by("-is_default", "price_paise", "id"), to_attr="_prefetched_active_variants"),
            "gallery_set", "specification_set", "size_set", "color_set",
        )
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(status="published")
        return get_object_or_404(queryset, slug=self.kwargs.get('slug'))


class CartApiView(generics.ListCreateAPIView):
    """
    Adds or updates one product line in a cart.

    The price is ALWAYS `ProductVariant.price_paise` from the database. Any `price`,
    `shipping_amount` or total sent by the client is ignored. The cart owner is the authenticated user, never a user id
    taken from the request body.
    """

    serializer_class = CartSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def get_queryset(self):
        # Listing every cart in the system is never allowed.
        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return Cart.objects.all()
        return Cart.objects.none()

    def create(self, request, *args, **kwargs):
        payload = request.data

        cart_id = str(payload.get('cart_id') or '').strip()
        if not cart_id or len(cart_id) > 1000:
            raise ValidationError({"cart_id": "A valid cart id is required."})

        try:
            qty = int(payload.get('qty'))
        except (TypeError, ValueError):
            raise ValidationError({"qty": "Quantity must be a whole number."})
        if qty < 1:
            raise ValidationError({"qty": "Quantity must be at least 1."})

        # Authorisation before anything else, so a rejected caller learns nothing about stock.
        requested_user = _optional_user_id(payload.get('user'))
        if requested_user is not None:
            ensure_self_or_staff(request, requested_user)
        user = request.user if request.user.is_authenticated else None

        product = Product.objects.filter(status="published", id=payload.get('product')).first()
        if product is None:
            raise ValidationError({"product": "This product is not available."})

        variant_id = payload.get('variant')
        if variant_id not in (None, "", "undefined", "null"):
            # The storefront's variant picker sends the exact sellable unit.
            try:
                variant = ProductVariant.objects.filter(pk=int(variant_id), product=product, active=True).first()
            except (TypeError, ValueError):
                variant = None
            if variant is None:
                raise ValidationError({"variant": "This option is not available."})
        else:
            variant = resolve_variant(product, payload.get('size'), payload.get('color'))
            if variant is None:
                raise ValidationError({"product": "This product has no sellable variant."})

        try:
            _cart, created = put_in_cart(
                cart_id, user, product, variant, qty,
                country=payload.get('country'), size=payload.get('size'), color=payload.get('color'),
            )
        except InsufficientStock as exc:
            raise ValidationError({"qty": f"Only {exc.available} left in stock."})

        if created:
            return Response({"message": "Cart Created Successfully"}, status=status.HTTP_201_CREATED)
        return Response({"message": "Cart updated successfully"}, status=status.HTTP_200_OK)


def put_in_cart(cart_id, user, product, variant, qty, country=None, size=None, color=None):
    """
    The one way a line gets into a cart: used by "add to cart", by a quantity change and by
    reorder. Sets the line to `qty` units of `variant` at today's price and holds the stock.
    Returns (cart_line, created). Raises InsufficientStock (and writes nothing) when the
    quantity is not available.
    """
    options = variant.options or {}
    size = size or options.get('Size') or variant.size or None
    color = color or options.get('Colour') or options.get('Color') or variant.color or None

    # One cart line per sellable unit. A row written before variants existed has no
    # variant; it is adopted by the first write for the same product.
    cart = Cart.objects.filter(cart_id=cart_id, variant=variant).first()
    if cart is None:
        cart = Cart.objects.filter(cart_id=cart_id, product=product, variant__isnull=True).first()
    created = cart is None
    if created:
        cart = Cart()

    cart.product = product
    cart.user = user
    cart.qty = qty
    cart.size = size
    cart.color = color
    cart.country = country
    cart.cart_id = cart_id
    cart.variant = variant

    # The line stores a snapshot of the unit price and line subtotal in paise (with their
    # Decimal mirrors). Shipping, discount and the payable total are per order and come
    # from store.pricing.quote(); no tax or service fee is ever added to a line.
    unit_price_paise = int(variant.price_paise)
    set_money(cart, "price", unit_price_paise)
    set_money(cart, "sub_total", unit_price_paise * qty)
    set_money(cart, "shipping_amount", 0)
    set_money(cart, "service_fee", 0)
    set_money(cart, "tax_fee", 0)
    set_money(cart, "total", unit_price_paise * qty)

    # Hold the stock. Existing holds for this cart line are released first so that
    # changing the quantity re-reserves the new amount rather than stacking holds.
    with transaction.atomic():
        _release_cart_line(cart_id, variant)
        reserve(variant, qty, cart_id=cart_id)
        cart.save()
    return cart, created


def _release_cart_line(cart_id, variant):
    """Release only this cart's holds for one variant."""
    from inventory.services import release

    holds = list(StockReservation.objects.filter(
        cart_id=cart_id, variant=variant, status=ReservationStatus.ACTIVE
    ))
    if holds:
        release(holds, reason="cart line replaced")


def _cart_queryset_for(request, cart_id, user_id, include_all_user_carts):
    """
    The lines of one cart. A cart is identified by its random cart id alone, which is also
    what an order is created from, so the list, the totals and the order always agree.
    When a user id is supplied it must be the caller's own (or the caller is staff).
    `include_all_user_carts` is accepted for backwards compatibility and ignored.
    """
    if user_id is not None:
        ensure_self_or_staff(request, user_id)
    return Cart.objects.filter(cart_id=cart_id)


class CartListView(generics.ListAPIView):
    serializer_class = CartSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return _cart_queryset_for(self.request, self.kwargs['cart_id'], self.kwargs.get('user_id'), True)


class CartTotalView(generics.ListAPIView):
    serializer_class = CartSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return _cart_queryset_for(self.request, self.kwargs['cart_id'], self.kwargs.get('user_id'), False)


class CartDetailView(generics.RetrieveAPIView):
    """
    Cart totals, computed by store.pricing.quote() from current variant prices.

    Every money value in the response is integer paise. An optional `?coupon=CODE` previews a
    coupon: an unusable code comes back with `coupon_error` and `coupon_message` and no discount.
    """

    serializer_class = CartSerializer
    lookup_field = 'cart_id'
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return _cart_queryset_for(self.request, self.kwargs['cart_id'], self.kwargs.get('user_id'), False)

    def get(self, request, *args, **kwargs):
        rows = list(self.get_queryset().select_related('product', 'variant').order_by('id'))

        lines = []
        cart_item_ids = []
        for row in rows:
            variant = variant_for_cart_line(row)
            qty = int(row.qty or 0)
            if variant is None or qty < 1:
                continue
            lines.append((variant, qty))
            cart_item_ids.append(row.id)

        customer = Customer.build(user=request.user)
        priced = quote(lines, coupon_code=request.GET.get('coupon'), customer=customer)

        data = priced.as_dict()
        for line, cart_item_id in zip(data["lines"], cart_item_ids):
            line["cart_item_id"] = cart_item_id
        return Response(data)


class CartItemDeleteView(generics.DestroyAPIView):
    serializer_class = CartSerializer
    lookup_field = 'cart_id'
    permission_classes = (AllowAny,)

    def get_object(self):
        cart_id = self.kwargs['cart_id']
        item_id = self.kwargs['item_id']
        user_id = self.kwargs.get('user_id')

        if user_id is not None:
            user_id = ensure_self_or_staff(self.request, user_id)
            return get_object_or_404(Cart, cart_id=cart_id, id=item_id, user_id=user_id)
        return get_object_or_404(Cart, cart_id=cart_id, id=item_id)

    def perform_destroy(self, instance):
        # Removing a line gives its held stock straight back.
        if instance.variant_id:
            _release_cart_line(instance.cart_id, instance.variant)
        instance.delete()


class CreateOrderView(generics.CreateAPIView):
    """
    Turn a cart into an order draft.

    Totals are never taken from the request: the order stores exactly what
    store.pricing.quote() returns for the cart's lines. Re-posting the same cart returns the
    same draft, refreshed from the cart as it is now (lines, quantities, contact details).
    """

    serializer_class = CartOrderSerializer
    queryset = CartOrder.objects.all()
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    REQUIRED_FIELDS = ('full_name', 'email', 'mobile', 'address', 'city', 'state', 'country', 'cart_id')

    def create(self, request, *args, **kwargs):
        payload = request.data

        missing = [f for f in self.REQUIRED_FIELDS if not str(payload.get(f) or '').strip()]
        if missing:
            raise ValidationError({f: "This field is required." for f in missing})

        cart_id = str(payload['cart_id']).strip()

        requested_user = _optional_user_id(payload.get('user_id'))
        if requested_user is not None:
            ensure_self_or_staff(request, requested_user)
        user = request.user if request.user.is_authenticated else None

        payment_method = str(payload.get('payment_method') or '').strip().upper()
        valid_methods = {choice[0] for choice in PAYMENT_METHOD_CHOICES}
        if payment_method and payment_method not in valid_methods:
            raise ValidationError({"payment_method": f"Choose one of: {', '.join(sorted(valid_methods))}."})

        customer = Customer.build(user=user, email=payload.get('email'), phone=payload.get('mobile'))

        with transaction.atomic():
            # One order draft per cart: re-submitting the same checkout returns the existing
            # unpaid order instead of creating a duplicate.
            existing = CartOrder.objects.select_for_update().filter(idempotency_key=cart_id).first()
            if existing is not None and (order_is_dead(existing) or existing.payment_status not in DRAFT_PAYMENT_STATUSES):
                # That order is finished with (paid, placed as COD, cancelled or expired). The
                # browser keeps its cart id, so whatever is in the cart now is a NEW order:
                # retire the old order's key and carry on.
                existing.idempotency_key = f"{cart_id}:retired:{existing.oid}"[:255]
                existing.save(update_fields=["idempotency_key"])
                existing = None

            cart_items = list(Cart.objects.filter(cart_id=cart_id).select_related('product', 'variant').order_by('id'))
            if not cart_items:
                raise ValidationError({"cart_id": "Your cart is empty."})

            lines = []
            for c in cart_items:
                variant = variant_for_cart_line(c)
                if variant is None:
                    raise ValidationError({"cart_id": f"{c.product.title} is no longer available."})
                lines.append((variant, int(c.qty or 0)))

            if 'coupon_code' in payload:
                coupon_code = str(payload.get('coupon_code') or '').strip()
            else:
                coupon_code = existing.coupon_code if existing is not None else ''

            # The coupon row is locked until this transaction commits, so two simultaneous
            # checkouts cannot both take the last use of a capped coupon.
            priced = quote(lines, coupon_code=coupon_code, customer=customer,
                           exclude_order=existing, lock_coupon=bool(coupon_code))

            order = existing if existing is not None else CartOrder(
                payment_status="processing", channel="WEBSITE", idempotency_key=cart_id,
            )
            order.buyer = user
            order.full_name = payload['full_name']
            order.email = payload['email']
            order.mobile = payload['mobile']
            order.address = payload['address']
            order.city = payload['city']
            order.state = payload['state']
            order.country = payload['country']
            order.pincode = str(payload.get('pincode') or '').strip()[:10]
            order.phone_e164 = customer.phone_e164
            order.payment_method = payment_method
            order.save()

            previous_items = {}
            if existing is not None:
                previous_items = {item.variant_id: item for item in CartOrderItem.objects.filter(order=order)}

            order_items = []
            item_by_variant = {}
            for c, (variant, _qty) in zip(cart_items, lines):
                order_item = previous_items.pop(variant.pk, None)
                if order_item is None:
                    order_item = CartOrderItem(order=order, product=c.product, variant=variant, vendor=c.product.vendor)
                order_item.color = c.color
                order_item.size = c.size
                order_items.append(order_item)
                if c.product.vendor_id:
                    order.vendor.add(c.product.vendor)

            # Lines that have left the cart since the draft was first created.
            for stale in previous_items.values():
                stale.delete()

            apply_quote_to_order(order, order_items, priced)
            record_redemption(order, priced, customer)

            for order_item in order_items:
                item_by_variant[order_item.variant_id] = order_item

            # The stock this cart was holding now belongs to the order.
            attach_reservations_to_order(cart_id, order, item_by_variant)

        return Response(
            {
                "message": "Order Created Successfully",
                "order_oid": order.oid,
                "total_paise": order.total_paise,
                "coupon_code": priced.coupon_code,
                "coupon_error": priced.coupon_error,
                "coupon_message": priced.coupon_message,
            },
            status=status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED,
        )


def _get_order_for_request(request, order_oid):
    order = CartOrder.objects.filter(oid=order_oid).order_by('-id').first()
    if order is None:
        return None
    ensure_order_access(request, order)
    return order


class CheckoutView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    lookup_field = 'order_oid'
    permission_classes = (AllowAny,)

    def get_object(self):
        order = _get_order_for_request(self.request, self.kwargs['order_oid'])
        if order is None:
            raise Http404("Order not found")
        return order


def _order_totals(order):
    return {
        "sub_total_paise": order.sub_total_paise,
        "saved_paise": order.saved_paise,
        "shipping_amount_paise": order.shipping_amount_paise,
        "tax_fee_paise": order.tax_fee_paise,
        "total_paise": order.total_paise,
        "coupon_code": order.coupon_code,
    }


class CouponApiView(generics.CreateAPIView):
    """
    Apply, replace or remove (blank code) the coupon on an unpaid order draft.

    The order is re-priced by store.pricing.quote() from the unit prices it already stores,
    the discount is spread over every line, and the redemption row is written in the same
    transaction with the coupon row locked.
    """

    serializer_class = CartOrderSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def create(self, request, *args, **kwargs):
        payload = request.data
        order_oid = payload.get('order_oid')
        coupon_code = str(payload.get('coupon_code') or '').strip()

        order = _get_order_for_request(request, order_oid)
        if order is None:
            return Response({"message": "Order Does Not Exists"}, status=status.HTTP_404_NOT_FOUND)
        if order.payment_status == "paid":
            return Response({"message": "Order is already paid"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            order = CartOrder.objects.select_for_update().get(pk=order.pk)
            if order.payment_status not in DRAFT_PAYMENT_STATUSES or order_is_dead(order):
                return Response({"message": "This order can no longer be changed."}, status=status.HTTP_400_BAD_REQUEST)

            order_items = list(CartOrderItem.objects.filter(order=order).select_related('product', 'variant').order_by('id'))
            lines = []
            for item in order_items:
                variant = item.variant if item.variant_id else default_variant_for(item.product)
                if variant is None or item.qty < 1:
                    return Response({"message": "This order can no longer be changed."}, status=status.HTTP_400_BAD_REQUEST)
                # Re-quote at the price the order already stores, not today's catalogue price.
                lines.append((variant, int(item.qty), int(item.price_paise)))
            if not lines:
                return Response({"message": "Order Item Does Not Exists"}, status=status.HTTP_400_BAD_REQUEST)

            customer = Customer.build(user=order.buyer, email=order.email, phone=order.phone_e164 or order.mobile)
            priced = quote(lines, coupon_code=coupon_code, customer=customer,
                           exclude_order=order, lock_coupon=bool(coupon_code))

            if coupon_code and priced.coupon is None:
                # Refused: the order keeps whatever it had before.
                return Response(
                    {"message": priced.coupon_message, "coupon_error": priced.coupon_error, **_order_totals(order)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            already_applied = bool(coupon_code) and order.coupon_code.lower() == priced.coupon_code.lower() \
                and order.saved_paise == priced.discount_paise
            apply_quote_to_order(order, order_items, priced)
            record_redemption(order, priced, customer)

        if not coupon_code:
            message = "Coupon Removed"
        elif already_applied:
            message = "Coupon Already Activated"
        else:
            message = "Coupon Activated"
        return Response({"message": message, "coupon_error": "", **_order_totals(order)}, status=status.HTTP_200_OK)


class StripeCheckoutView(generics.CreateAPIView):
    """
    Reached by a plain HTML form POST (browser navigation), so no JWT is available here.
    The order's random oid is the capability; the amount always comes from the database.
    """

    serializer_class = CartOrderSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def create(self, request, *args, **kwargs):
        if not payments.is_enabled(payments.STRIPE):
            return Response({'error': 'This payment method is not available.'}, status=status.HTTP_403_FORBIDDEN)
        order = CartOrder.objects.filter(oid=self.kwargs['order_oid']).order_by('-id').first()
        if not order:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        if order.payment_status == "paid":
            return Response({'error': 'Order is already paid'}, status=status.HTTP_400_BAD_REQUEST)
        if order.payment_status not in DRAFT_PAYMENT_STATUSES or order_is_dead(order):
            return Response({'error': 'This order is not awaiting payment.'}, status=status.HTTP_400_BAD_REQUEST)
        # A payment session stays open for up to a day, and unpaid drafts are expired after
        # ORDER_DRAFT_TTL_HOURS; never start a payment that could outlive its order.
        if timezone.now() - order.date > timedelta(hours=max(settings.ORDER_DRAFT_TTL_HOURS - 25, 1)):
            return Response({'error': 'This checkout has expired. Please start again from your cart.'}, status=status.HTTP_400_BAD_REQUEST)
        if order.total_paise < 1:
            return Response({'error': 'There is nothing to pay on this order.'}, status=status.HTTP_400_BAD_REQUEST)
        if not settings.STRIPE_SECRET_KEY:
            return Response({'error': 'Card payments are not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=order.email,
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'inr',
                            'product_data': {
                                'name': order.full_name,
                            },
                            # Integer paise straight from the stored quote; never recomputed here.
                            'unit_amount': int(order.total_paise),
                        },
                        'quantity': 1,
                    }
                ],
                mode='payment',
                client_reference_id=order.oid,
                success_url=settings.SITE_URL + '/payment-success/' + order.oid + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.SITE_URL + '/?session_id={CHECKOUT_SESSION_ID}',
            )
            order.stripe_session_id = checkout_session.id
            order.save()

            return redirect(checkout_session.url)
        except stripe.error.StripeError:
            logger.exception("stripe checkout session creation failed for order %s", order.pk)
            return Response({'error': 'Something went wrong when creating the card payment session.'}, status=status.HTTP_502_BAD_GATEWAY)


def get_access_token(client_id, secret_key):
    """Obtain a PayPal OAuth access token. The token is never logged."""
    token_url = f"{settings.PAYPAL_API_BASE}/v1/oauth2/token"
    data = {'grant_type': 'client_credentials'}
    response = requests.post(token_url, data=data, auth=(client_id, secret_key), timeout=EXTERNAL_TIMEOUT_SECONDS)
    if response.status_code == 200:
        return response.json()['access_token']
    raise Exception(f'Failed to get access token from PayPal. Status code: {response.status_code}')


def _paypal_amount_matches(paypal_order_data, order):
    """
    Fail closed: the captured PayPal order must be for exactly this order's total in USD.
    Reads purchase_units[0].amount.{currency_code,value} from the PayPal v2 order.
    """
    try:
        amount = paypal_order_data['purchase_units'][0]['amount']
        currency = str(amount['currency_code']).upper()
        value = Decimal(str(amount['value']))
    except (KeyError, IndexError, TypeError, InvalidOperation):
        return False
    # Legacy path, hidden from checkout since G1 (ROADMAP A6): PayPal cannot settle in INR, so
    # this still compares the USD figure against the order's number. The amount is read from
    # the paise column, never from the Decimal mirror.
    return currency == "USD" and value == from_paise(int(order.total_paise))


def _clear_cart_for_order(order):
    """
    Empty the cart once its order is paid.

    The cart was never cleared before, so a customer who paid and came back saw their
    old items again and could reserve stock twice. Reservations stay attached to the
    order, so deleting the cart rows does not give the stock back.
    """
    if order.idempotency_key:
        Cart.objects.filter(cart_id=order.idempotency_key).delete()


def _send_order_emails_and_notifications(order, order_items, notify_customer_by_email):
    if order.buyer is not None:
        send_notification(user=order.buyer, order=order)

    merge_data = {'order': order, 'order_items': order_items}

    if notify_customer_by_email:
        try:
            text_body = render_to_string("email/customer_order_confirmation.txt", merge_data)
            html_body = render_to_string("email/customer_order_confirmation.html", merge_data)
            msg = EmailMultiAlternatives(
                subject="Order Placed Successfully", from_email=settings.FROM_EMAIL,
                to=[order.email], body=text_body
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()
        except Exception:
            logger.exception("order confirmation email failed for order %s", order.pk)

    for o in order_items:
        send_notification(vendor=o.vendor, order=order, order_item=o)
        if notify_customer_by_email and o.vendor is not None and o.vendor.email:
            try:
                text_body = render_to_string("email/vendor_order_sale.txt", merge_data)
                html_body = render_to_string("email/vendor_order_sale.html", merge_data)
                msg = EmailMultiAlternatives(
                    subject="New Sale!", from_email=settings.FROM_EMAIL,
                    to=[o.vendor.email], body=text_body
                )
                msg.attach_alternative(html_body, "text/html")
                msg.send()
            except Exception:
                logger.exception("sale email failed for order %s item %s", order.pk, o.pk)


class PaymentSuccessView(generics.CreateAPIView):
    """
    Verifies a payment with the provider and marks the order paid exactly once.

    * PayPal: the PayPal order must be COMPLETED, for this order's exact amount and currency,
      and its id may be used for one order only (replay protection via core.ProcessedEvent).
    * Stripe: the session id must be the one created for this order and must be paid.
    """

    serializer_class = CartOrderSerializer
    queryset = CartOrder.objects.all()
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def create(self, request, *args, **kwargs):
        payload = request.data

        order_oid = payload.get('order_oid')
        session_id = str(payload.get('session_id') or 'null')
        paypal_order_id = str(payload.get('payapl_order_id') or 'null')

        order = _get_order_for_request(request, order_oid)
        if order is None:
            return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        order_items = CartOrderItem.objects.filter(order=order)

        if paypal_order_id not in ("null", "undefined", ""):
            if not payments.is_enabled(payments.PAYPAL):
                return Response({"message": "This payment method is not available."}, status=status.HTTP_403_FORBIDDEN)
            if not (PAYPAL_CLIENT_ID and PAYPAL_SECRET_ID):
                return Response({"message": "PayPal is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            paypal_api_url = f"{settings.PAYPAL_API_BASE}/v2/checkout/orders/{paypal_order_id}"
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {get_access_token(PAYPAL_CLIENT_ID, PAYPAL_SECRET_ID)}',
                }
                response = requests.get(paypal_api_url, headers=headers, timeout=EXTERNAL_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("paypal verification request failed for order %s", order.pk)
                return Response({"message": "Could not verify PayPal payment."}, status=status.HTTP_502_BAD_GATEWAY)

            if response.status_code != 200:
                return Response({"message": "Could not verify PayPal payment."}, status=status.HTTP_502_BAD_GATEWAY)

            paypal_order_data = response.json()
            if paypal_order_data.get('status') != 'COMPLETED':
                return Response({"message": "unpaid!"}, status=status.HTTP_402_PAYMENT_REQUIRED)
            if not _paypal_amount_matches(paypal_order_data, order):
                logger.warning("paypal amount/currency mismatch for order %s", order.pk)
                return Response({"message": "Payment amount does not match this order."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                order = CartOrder.objects.select_for_update().get(pk=order.pk)
                if order.payment_status == "paid":
                    return Response({"message": "Already Paid"}, status=status.HTTP_201_CREATED)
                if not claim_event("paypal", paypal_order_id, note=f"order:{order.pk}"):
                    logger.warning("paypal order id replay attempt against order %s", order.pk)
                    return Response({"message": "This payment has already been used."}, status=status.HTTP_409_CONFLICT)
                if order.payment_status != "processing":
                    return Response({"message": "Order is not awaiting payment."}, status=status.HTTP_400_BAD_REQUEST)
                mark_paid(order, reason="paypal verified")
                _clear_cart_for_order(order)

            _send_order_emails_and_notifications(order, order_items, notify_customer_by_email=True)
            return Response({"message": "Payment Successfull"}, status=status.HTTP_201_CREATED)

        if session_id not in ("null", "undefined", ""):
            if not payments.is_enabled(payments.STRIPE):
                return Response({"message": "This payment method is not available."}, status=status.HTTP_403_FORBIDDEN)
            if not order.stripe_session_id or session_id != order.stripe_session_id:
                logger.warning("stripe session mismatch for order %s", order.pk)
                return Response({"message": "This payment session does not belong to this order."}, status=status.HTTP_400_BAD_REQUEST)
            if not settings.STRIPE_SECRET_KEY:
                return Response({"message": "Card payments are not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            try:
                session = stripe.checkout.Session.retrieve(session_id)
            except stripe.error.StripeError:
                logger.exception("stripe session retrieval failed for order %s", order.pk)
                return Response({"message": "Could not verify card payment."}, status=status.HTTP_502_BAD_GATEWAY)

            if session.payment_status == "paid":
                with transaction.atomic():
                    order = CartOrder.objects.select_for_update().get(pk=order.pk)
                    if order.payment_status == "paid":
                        return Response({"message": "Already Paid"}, status=status.HTTP_201_CREATED)
                    if not claim_event("stripe_session", session_id, note=f"order:{order.pk}"):
                        return Response({"message": "Already Paid"}, status=status.HTTP_201_CREATED)
                    if order.payment_status != "processing":
                        return Response({"message": "Order is not awaiting payment."}, status=status.HTTP_400_BAD_REQUEST)
                    mark_paid(order, reason="stripe verified")
                    _clear_cart_for_order(order)

                _send_order_emails_and_notifications(order, order_items, notify_customer_by_email=False)
                return Response({"message": "Payment Successfull"}, status=status.HTTP_201_CREATED)
            elif session.payment_status == "unpaid":
                return Response({"message": "unpaid!"}, status=status.HTTP_402_PAYMENT_REQUIRED)
            elif session.payment_status == "canceled":
                return Response({"message": "cancelled!"}, status=status.HTTP_403_FORBIDDEN)
            return Response({"message": "An Error Occured!"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "No payment reference supplied."}, status=status.HTTP_400_BAD_REQUEST)


def delivered_line_for(user, product):
    """The delivered order line that entitles `user` to review `product`, or None."""
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        CartOrderItem.objects.filter(order__buyer=user, product=product, delivery_status="Delivered")
        .exclude(order__order_status="Cancelled")
        .order_by("-id")
        .first()
    )


def review_eligibility(user, product):
    """(eligible, reason, order_item). reason is "", "login", "not_purchased" or "already_reviewed"."""
    if not getattr(user, "is_authenticated", False):
        return False, "login", None
    if Review.objects.filter(user=user, product=product).exists():
        return False, "already_reviewed", None
    line = delivered_line_for(user, product)
    if line is None:
        return False, "not_purchased", None
    return True, "", line


class ReviewEligibilityView(generics.GenericAPIView):
    """Tells the product page whether to show the review form to this visitor."""

    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=self.kwargs['product_id'])
        eligible, reason, _line = review_eligibility(request.user, product)
        return Response({"eligible": eligible, "reason": reason})


class ReviewRatingAPIView(generics.CreateAPIView):
    """
    Reviews come from verified buyers only: the signed-in user must own an order with a
    delivered line for the product. One review per customer per product. A new review is
    PENDING and becomes public only when the owner approves it.
    """

    serializer_class = ReviewSerializer
    queryset = Review.objects.all()
    permission_classes = (IsAuthenticated,)
    throttle_scope = "review"

    def create(self, request, *args, **kwargs):
        payload = request.data

        requested_user = _optional_user_id(payload.get('user_id'))
        if requested_user is not None:
            ensure_self_or_staff(request, requested_user)

        product = get_object_or_404(Product, id=payload.get('product_id'))

        try:
            rating = int(payload.get('rating'))
        except (TypeError, ValueError):
            raise ValidationError({"rating": "Rating must be a number from 1 to 5."})
        if rating < 1 or rating > 5:
            raise ValidationError({"rating": "Rating must be a number from 1 to 5."})

        review = str(payload.get('review') or '').strip()
        if not review:
            raise ValidationError({"review": "Review text is required."})

        eligible, reason, line = review_eligibility(request.user, product)
        if reason == "already_reviewed":
            raise ValidationError({"review": "You have already reviewed this product."})
        if not eligible:
            raise PermissionDenied("Only customers who have received this product can review it.")

        Review.objects.create(user=request.user, product=product, rating=rating, review=review[:5000],
                              order_item=line, status=REVIEW_PENDING)
        return Response(
            {"message": "Thank you. Your review will appear once it has been checked.", "status": REVIEW_PENDING},
            status=status.HTTP_201_CREATED,
        )


class ReviewListView(generics.ListAPIView):
    """Public: approved reviews only."""

    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        product = get_object_or_404(Product, id=self.kwargs['product_id'])
        return Review.objects.filter(product=product, status=REVIEW_APPROVED)


class ReorderView(generics.GenericAPIView):
    """
    "Buy again": put every line of a past order back into the caller's cart, at TODAY's price
    and TODAY's availability, through the normal cart path (so stock is reserved). It never
    places an order. The response says what was added, what was reduced and what could not
    be added.
    """

    serializer_class = CartOrderSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def post(self, request, *args, **kwargs):
        order = _get_order_for_request(request, self.kwargs['order_oid'])
        if order is None:
            raise Http404("Order not found")
        if order.buyer_id is None:
            # A guest order's id is a capability for checkout only, not for copying its contents.
            raise PermissionDenied("Sign in to buy this order again.")

        cart_id = str(request.data.get('cart_id') or '').strip()
        if not cart_id or len(cart_id) > 1000:
            raise ValidationError({"cart_id": "A valid cart id is required."})
        user = request.user if request.user.is_authenticated else None

        added, reduced, unavailable = [], [], []
        for item in CartOrderItem.objects.filter(order=order).select_related('product', 'variant').order_by('id'):
            variant = item.variant if item.variant_id else default_variant_for(item.product)
            label = item.product.title
            if variant is not None and variant.name and variant.name != "Default":
                label = f"{label} ({variant.name})"
            if variant is None or not variant.active or item.product.status != "published":
                unavailable.append({"title": label, "wanted": item.qty, "reason": "discontinued"})
                continue

            # What this cart may take: free stock plus what this cart already holds of it.
            already_held = sum(
                r.quantity for r in StockReservation.objects.filter(
                    cart_id=cart_id, variant=variant, status=ReservationStatus.ACTIVE, order__isnull=True)
            )
            from inventory.services import available_qty

            can_take = available_qty(variant) + already_held
            qty = min(int(item.qty), can_take)
            if qty < 1:
                unavailable.append({"title": label, "wanted": item.qty, "reason": "sold_out"})
                continue
            try:
                put_in_cart(cart_id, user, item.product, variant, qty)
            except InsufficientStock:
                unavailable.append({"title": label, "wanted": item.qty, "reason": "sold_out"})
                continue
            entry = {"title": label, "variant_id": variant.pk, "qty": qty, "wanted": item.qty,
                     "unit_price_paise": int(variant.price_paise)}
            (added if qty == item.qty else reduced).append(entry)

        return Response({"added": added, "reduced": reduced, "unavailable": unavailable,
                         "cart_lines": Cart.objects.filter(cart_id=cart_id).count()})


class SearchProductsAPIView(CatalogueListMixin, generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        query = (self.request.GET.get('query') or '').strip()
        if not query:
            return Product.objects.none()
        return super().get_queryset().filter(title__icontains=query[:100])