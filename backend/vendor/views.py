# Django Packages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseNotFound, HttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.db import models
from django.db import transaction
from django.urls import reverse
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import default_storage
from django.db.models.functions import ExtractMonth
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string

# Restframework Packages
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

# Platform
from core.audit import record
from core.permissions import IsStaffOwner, PublicReadStaffWrite, ensure_self_or_staff

# Serializers
from userauths.serializer import MyTokenObtainPairSerializer, ProfileSerializer, RegisterSerializer
from store.serializers import CancelledOrderSerializer, CouponSummarySerializer, EarningSummarySerializer, NotificationSerializer, CartSerializer, NotificationSummarySerializer, SummarySerializer, CartOrderItemSerializer, CouponUsersSerializer,  ProductSerializer, TagSerializer, CategorySerializer, DeliveryCouriersSerializer, CartOrderSerializer, GallerySerializer, BrandSerializer, ProductFaqSerializer, ReviewSerializer,  SpecificationSerializer, CouponSerializer, ColorSerializer, SizeSerializer, AddressSerializer, WishlistSerializer, ConfigSettingsSerializer, VendorSerializer

# Models
from userauths.models import Profile, User
from store.models import CancelledOrder, Notification, CartOrderItem, CouponUsers, Cart, Product, Tag, Category, DeliveryCouriers, CartOrder, Gallery, Brand, ProductFaq, Review,  Specification, Coupon, Color, Size, Address, Wishlist
from addon.models import ConfigSettings, Tax
from vendor.models import Vendor

# Others Packages
import json
from decimal import Decimal
import stripe
import requests
from datetime import datetime, timedelta
import calendar
import urllib.parse
import requests
import stripe
from datetime import datetime as d


class DashboardStatsAPIView(generics.ListAPIView):
    serializer_class = SummarySerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):

        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)

        # Calculate summary values
        product_count = Product.objects.filter(vendor=vendor).count()
        order_count = CartOrder.objects.filter(
            vendor=vendor, payment_status="paid").count()
        revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F('sub_total') + models.F('shipping_amount')))['total_revenue'] or 0

        # Return a dummy list as we only need one summary object
        return [{
            'products': product_count,
            'orders': order_count,
            'revenue': revenue
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ProductsAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        products = Product.objects.filter(vendor=vendor)
        return products


class OrdersAPIView(generics.ListAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        orders = CartOrder.objects.filter(vendor=vendor, payment_status="paid")
        return orders


class RevenueAPIView(generics.ListAPIView):
    serializer_class = CartOrderItemSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F('sub_total') + models.F('shipping_amount')))['total_revenue'] or 0
        return revenue


class YearlyOrderReportChartAPIView(generics.ListAPIView):
    serializer_class = CartOrderItemSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)

        # Include the 'product' field in the queryset
        report = CartOrderItem.objects.filter(
            vendor=vendor,
            order__payment_status="paid"
        ).select_related('product').values(
            'order__date', 'product'
        ).annotate(models.Count('id'))

        return report


@api_view(('GET',))
@permission_classes([IsStaffOwner])
def MonthlyOrderChartAPIFBV(request, vendor_id):
    vendor = Vendor.objects.get(id=vendor_id)
    orders = CartOrder.objects.filter(vendor=vendor)
    orders_by_month = orders.annotate(month=ExtractMonth("date")).values(
        "month").annotate(orders=models.Count("id")).order_by("month")
    return Response(orders_by_month)


@api_view(('GET',))
@permission_classes([IsStaffOwner])
def MonthlyProductsChartAPIFBV(request, vendor_id):
    vendor = Vendor.objects.get(id=vendor_id)
    products = Product.objects.filter(vendor=vendor)
    products_by_month = products.annotate(month=ExtractMonth("date")).values(
        "month").annotate(orders=models.Count("id")).order_by("month")
    return Response(products_by_month)


# Values a browser form sends for "nothing": an empty box, or a null/undefined turned into
# text on its way into the form data.
BLANK_FORM_VALUES = ("", "null", "undefined", "none", "nan")


def is_blank_form_value(value):
    if value is None:
        return True
    if hasattr(value, "read"):  # an uploaded file is never blank
        return False
    return str(value).strip().lower() in BLANK_FORM_VALUES


def drop_blank_rows(rows, ignore_keys=()):
    """
    Keep only the repeatable rows the owner actually filled in.

    Every repeatable section of the product form (Specification, Color, Size, Gallery) always
    submits one empty row until it is used, and an untouched row must not fail the save. A row
    where even one field has a real value is kept, so a half-filled row still reports its own
    error instead of being silently dropped.
    """
    kept = []
    for row in rows:
        values = [value for key, value in row.items() if key not in ignore_keys]
        if any(not is_blank_form_value(value) for value in values):
            kept.append(row)
    return kept


class ProductCreateView(generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = (IsStaffOwner,)

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.is_valid(raise_exception=True)
        serializer.save()
        product_instance = serializer.instance

        specifications_data = []
        colors_data = []
        sizes_data = []
        gallery_data = []
        # Loop through the keys of self.request.data
        for key, value in self.request.data.items():
            # Example key: specifications[0][title]
            if key.startswith('specifications') and '[title]' in key:
                # Extract index from key
                index = key.split('[')[1].split(']')[0]
                title = value
                content_key = f'specifications[{index}][content]'
                content = self.request.data.get(content_key)
                specifications_data.append(
                    {'title': title, 'content': content})

            # Example key: colors[0][name]
            elif key.startswith('colors') and '[name]' in key:
                # Extract index from key
                index = key.split('[')[1].split(']')[0]
                name = value
                color_code_key = f'colors[{index}][color_code]'
                color_code = self.request.data.get(color_code_key)
                image_key = f'colors[{index}][image]'
                image = self.request.data.get(image_key)
                colors_data.append(
                    {'name': name, 'color_code': color_code, 'image': image})

            # Example key: sizes[0][name]
            elif key.startswith('sizes') and '[name]' in key:
                # Extract index from key
                index = key.split('[')[1].split(']')[0]
                name = value
                price_key = f'sizes[{index}][price]'
                price = self.request.data.get(price_key)
                sizes_data.append({'name': name, 'price': price})

            # Example key: gallery[0][image]
            elif key.startswith('gallery') and '[image]' in key:
                # Extract index from key
                index = key.split('[')[1].split(']')[0]
                image = value
                gallery_data.append({'image': image})

        # Log or print the data for debugging

        # Save nested serializers with the product instance
        self.save_nested_data(
            product_instance, SpecificationSerializer, specifications_data)
        self.save_nested_data(product_instance, ColorSerializer, colors_data)
        self.save_nested_data(product_instance, SizeSerializer, sizes_data)
        self.save_nested_data(
            product_instance, GallerySerializer, gallery_data)

    def save_nested_data(self, product_instance, serializer_class, data):
        rows = drop_blank_rows(data)
        if not rows:
            return
        serializer = serializer_class(data=rows, many=True, context={
                                      'product_instance': product_instance})
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product_instance)


class ProductUpdateAPIView(generics.RetrieveUpdateAPIView):
    """
    Update a product and its specifications, colours, sizes and gallery.

    The edit screen loads the product and posts every field back, so image fields arrive as
    the URL strings they were served as (e.g. "http://host/media/user_1/11.jpg") rather than
    as uploaded files. Those are resolved back to the stored file path where possible and
    otherwise dropped, so an edit that does not touch an image leaves that image alone.
    """

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = (IsStaffOwner,)

    # Computed/read-only values the edit form echoes back; they are never writable.
    NON_WRITABLE_KEYS = {
        'id', 'sku', 'pid', 'slug', 'date', 'vendor', 'gallery', 'specification', 'size',
        'color', 'product_rating', 'rating_count', 'order_count', 'get_precentage', 'in_stock',
    }

    def get_object(self):
        vendor = get_object_or_404(Vendor, id=self.kwargs['vendor_id'])
        return get_object_or_404(Product, vendor=vendor, pid=self.kwargs['product_pid'])

    @staticmethod
    def is_uploaded_file(value):
        return hasattr(value, 'read') and hasattr(value, 'name')

    @staticmethod
    def existing_media_path(value):
        """
        Turn an image value the form echoed back into the stored relative path, or None.

        Accepts a full media URL, a MEDIA_URL-prefixed path or a bare relative path, and only
        returns it when that file actually exists in storage.
        """
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate or candidate in ('undefined', 'null', 'None'):
            return None
        parsed = urllib.parse.urlparse(candidate)
        path = urllib.parse.unquote(parsed.path or candidate)
        media_url = urllib.parse.urlparse(settings.MEDIA_URL).path or '/media/'
        if not media_url.startswith('/'):
            media_url = '/' + media_url
        if path.startswith(media_url):
            path = path[len(media_url):]
        path = path.lstrip('/')
        if not path or '..' in path:
            return None
        try:
            return path if default_storage.exists(path) else None
        except (NotImplementedError, SuspiciousOperation, ValueError):
            return None

    def clean_product_data(self, data):
        """Writable product fields only, with echoed-back image values removed."""
        cleaned = {}
        for key in data.keys():
            if key in self.NON_WRITABLE_KEYS or '[' in key:
                continue
            value = data[key]
            if key == 'image' and not self.is_uploaded_file(value):
                # Not a new upload: leave the stored image untouched.
                continue
            cleaned[key] = value

        category = data.get('category')
        if category is not None:
            try:
                cleaned['category'] = int(category)
            except (TypeError, ValueError):
                # The form posts the whole category object when it was not changed.
                cleaned.pop('category', None)
        return cleaned

    def resolve_nested_image(self, value):
        """Return an uploaded file as-is, an echoed URL as its stored path, anything else None."""
        if self.is_uploaded_file(value):
            return value
        return self.existing_media_path(value)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        product = self.get_object()

        # partial=True: the form posts a subset of writable fields, and anything it omits keeps
        # its current value instead of being reset.
        serializer = self.get_serializer(product, data=self.clean_product_data(request.data), partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        category_id = self.clean_product_data(request.data).get('category')
        if isinstance(category_id, int):
            product.category = Category.objects.filter(id=category_id).first()
            product.save(update_fields=['category'])

        specifications_data = []
        colors_data = []
        sizes_data = []
        gallery_data = []
        for key, value in request.data.items():
            if key.startswith('specifications') and '[title]' in key:
                index = key.split('[')[1].split(']')[0]
                title = value
                content = request.data.get(f'specifications[{index}][content]')
                if str(title or '').strip():
                    specifications_data.append({'title': title, 'content': content})

            elif key.startswith('colors') and '[name]' in key:
                index = key.split('[')[1].split(']')[0]
                name = value
                color_code = request.data.get(f'colors[{index}][color_code]')
                image = self.resolve_nested_image(request.data.get(f'colors[{index}][image]'))
                if str(name or '').strip():
                    entry = {'name': name, 'color_code': color_code}
                    if self.is_uploaded_file(image):
                        entry['image'] = image
                    elif image is not None:
                        # An existing file already in storage: a path string cannot pass
                        # FileField validation, so it is attached after the row is created.
                        entry['_existing_image'] = image
                    colors_data.append(entry)

            elif key.startswith('sizes') and '[name]' in key:
                index = key.split('[')[1].split(']')[0]
                name = value
                price = request.data.get(f'sizes[{index}][price]')
                if str(name or '').strip():
                    sizes_data.append({'name': name, 'price': price})

            elif key.startswith('gallery') and '[image]' in key:
                image = self.resolve_nested_image(value)
                if self.is_uploaded_file(image):
                    gallery_data.append({'image': image})
                elif image is not None:
                    gallery_data.append({'_existing_image': image})

        # A section is only replaced when the request actually carried entries for it, so an
        # edit that touches nothing but the price cannot wipe the gallery or the colours.
        sections = [
            ('specifications', product.specification(), SpecificationSerializer, specifications_data),
            ('colors', product.color(), ColorSerializer, colors_data),
            ('sizes', product.size(), SizeSerializer, sizes_data),
            ('gallery', product.gallery(), GallerySerializer, gallery_data),
        ]
        for prefix, existing_queryset, serializer_class, entries in sections:
            submitted = any(k.startswith(prefix) and '[' in k for k in request.data.keys())
            # Replace a section only when the request carried usable entries for it. A section
            # that was not submitted, or whose entries were all placeholders, is left untouched:
            # editing a price must never wipe the gallery. Clearing a section entirely is done
            # from Django admin.
            if not submitted or not entries:
                continue
            existing_queryset.delete()
            self.save_nested_data(product, serializer_class, entries)

        return Response({'message': 'Product Updated'}, status=status.HTTP_200_OK)

    def save_nested_data(self, product_instance, serializer_class, data):
        """
        Save nested rows. Entries may carry `_existing_image`: the storage path of a file that
        is already uploaded. FileField validation only accepts uploads, so that path is set on
        the row after it is created rather than passed through the serializer.
        """
        # A repeatable section the owner left blank submits one empty row; skip those rather
        # than failing the whole save. A row that only carries an already-uploaded image is kept.
        # A row that carries only an already-uploaded image is still a real row.
        data = [row for row in data
                if row in drop_blank_rows(data, ignore_keys=("_existing_image",)) or row.get("_existing_image")]
        if not data:
            return
        existing_images = [entry.pop('_existing_image', None) for entry in data]
        serializer = serializer_class(data=data, many=True, context={
                                      'product_instance': product_instance})
        serializer.is_valid(raise_exception=True)
        instances = serializer.save(product=product_instance)

        for instance, image_path in zip(instances, existing_images):
            if image_path and hasattr(instance, 'image'):
                instance.image.name = image_path
                instance.save(update_fields=['image'])


class ProductDeleteAPIView(generics.DestroyAPIView):
    """
    Delete a product.

    A product can only be deleted while it has no history. Once it has stock in the ledger or
    has appeared on an order, deleting it would erase permanent records (the stock ledger and
    the audit trail are append-only), so the request is refused with an explanation and the
    owner is pointed at "hide from the shop" instead, which is reversible.
    """

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        vendor = get_object_or_404(Vendor, id=self.kwargs['vendor_id'])
        return get_object_or_404(Product, vendor=vendor, pid=self.kwargs['product_pid'])

    def destroy(self, request, *args, **kwargs):
        from inventory.models import Batch, StockMovement
        from store.models import CartOrderItem

        product = self.get_object()
        variant_ids = list(product.variants.values_list("id", flat=True))

        reasons = []
        if CartOrderItem.objects.filter(product=product).exists():
            reasons.append("it has been ordered")
        if StockMovement.objects.filter(variant_id__in=variant_ids).exists():
            reasons.append("it has stock history")
        elif Batch.objects.filter(variant_id__in=variant_ids).exists():
            reasons.append("it has a production batch")

        if reasons:
            return Response(
                {
                    "message": (
                        f"\"{product.title}\" cannot be deleted because {' and '.join(reasons)}. "
                        "Deleting it would erase records that have to be kept. "
                        "Hide it from the shop instead: it disappears from the storefront straight "
                        "away and you can bring it back at any time."
                    ),
                    "can_hide": True,
                    "status": product.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            record("product.deleted", product, before={"title": product.title, "status": product.status},
                   after=None, reason="deleted from the dashboard", actor=request.user)
            product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductVisibilityAPIView(APIView):
    """
    Hide a product from the shop, or put it back.

    POST {"status": "published" | "draft" | "disabled"}. Hiding is the reversible alternative to
    deleting a product that has history; a hidden product keeps its orders, stock and reviews.
    """

    permission_classes = (IsStaffOwner,)

    ALLOWED = ("published", "draft", "disabled")

    def post(self, request, vendor_id, product_pid, *args, **kwargs):
        vendor = get_object_or_404(Vendor, id=vendor_id)
        product = get_object_or_404(Product, vendor=vendor, pid=product_pid)

        target = str(request.data.get("status") or "").strip().lower()
        if target not in self.ALLOWED:
            return Response({"message": f"Status must be one of: {', '.join(self.ALLOWED)}."},
                            status=status.HTTP_400_BAD_REQUEST)

        before = product.status
        if before != target:
            product.status = target
            product.save(update_fields=["status"])
            record("product.status", product, before={"status": before}, after={"status": target},
                   reason="changed from the dashboard", actor=request.user)
        return Response({"pid": product.pid, "title": product.title, "status": product.status})


class FilterProductsAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        filter = self.request.GET.get('filter')


        vendor = Vendor.objects.get(id=vendor_id)
        if filter == "published":
            products = Product.objects.filter(
                vendor=vendor, status="published")
        elif filter == "draft":
            products = Product.objects.filter(vendor=vendor, status="draft")
        elif filter == "disabled":
            products = Product.objects.filter(vendor=vendor, status="disabled")
        elif filter == "in-review":
            products = Product.objects.filter(
                vendor=vendor, status="in-review")
        elif filter == "latest":
            products = Product.objects.filter(vendor=vendor).order_by('-id')
        elif filter == "oldest":
            products = Product.objects.filter(vendor=vendor).order_by('id')
        else:
            products = Product.objects.filter(vendor=vendor)
        return products


class OrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        vendor_id = self.kwargs['vendor_id']
        order_oid = self.kwargs['order_oid']

        vendor = Vendor.objects.get(id=vendor_id)
        order = CartOrder.objects.get(
            vendor=vendor, payment_status="paid", oid=order_oid)
        return order


class Earning(generics.ListAPIView):
    serializer_class = EarningSummarySerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):

        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)

        one_month_ago = datetime.today() - timedelta(days=28)
        monthly_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid", date__gte=one_month_ago).aggregate(
            total_revenue=models.Sum(models.F('sub_total') + models.F('shipping_amount')))['total_revenue'] or 0
        total_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F('sub_total') + models.F('shipping_amount')))['total_revenue'] or 0

        return [{
            'monthly_revenue': monthly_revenue,
            'total_revenue': total_revenue,
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@api_view(('GET',))
@permission_classes([IsStaffOwner])
def MonthlyEarningTracker(request, vendor_id):
    vendor = Vendor.objects.get(id=vendor_id)
    monthly_earning_tracker = (
        CartOrderItem.objects
        .filter(vendor=vendor, order__payment_status="paid")
        .annotate(
            month=ExtractMonth("date")
        )
        .values("month")
        .annotate(
            sales_count=models.Sum("qty"),
            total_earning=models.Sum(
                models.F('sub_total') + models.F('shipping_amount'))
        )
        .order_by("-month")
    )
    return Response(monthly_earning_tracker)


class ReviewsListAPIView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        reviews = Review.objects.filter(product__vendor=vendor)
        return reviews


class ReviewsDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        vendor_id = self.kwargs['vendor_id']
        review_id = self.kwargs['review_id']

        vendor = Vendor.objects.get(id=vendor_id)
        review = Review.objects.get(product__vendor=vendor, id=review_id)
        return review



class CouponListAPIView(generics.ListAPIView):
    serializer_class = CouponSerializer
    queryset = Coupon.objects.all()
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        coupon = Coupon.objects.filter(vendor=vendor)
        return coupon


class CouponCreateAPIView(generics.CreateAPIView):
    serializer_class = CouponSerializer
    queryset = Coupon.objects.all()
    permission_classes = (IsStaffOwner,)

    def create(self, request, *args, **kwargs):
        payload = request.data

        vendor_id = payload['vendor_id']
        code = payload['code']
        discount = payload['discount']
        active = payload['active']


        vendor = Vendor.objects.get(id=vendor_id)
        coupon = Coupon.objects.create(
            vendor=vendor,
            code=code,
            discount=discount,
            active=(active.lower() == "true")
        )

        return Response({"message": "Coupon Created Successfully."}, status=status.HTTP_201_CREATED)


class CouponDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CouponSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        vendor_id = self.kwargs['vendor_id']
        coupon_id = self.kwargs['coupon_id']

        vendor = Vendor.objects.get(id=vendor_id)

        coupon = Coupon.objects.get(vendor=vendor, id=coupon_id)
        return coupon


class CouponStats(generics.ListAPIView):
    serializer_class = CouponSummarySerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):

        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)

        total_coupons = Coupon.objects.filter(vendor=vendor).count()
        active_coupons = Coupon.objects.filter(
            vendor=vendor, active=True).count()

        return [{
            'total_coupons': total_coupons,
            'active_coupons': active_coupons,
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class NotificationUnSeenListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        notifications = Notification.objects.filter(vendor=vendor, seen=False).order_by('seen')
        return notifications
    
class NotificationSeenListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)
        notifications = Notification.objects.filter(vendor=vendor, seen=True).order_by('seen')
        return notifications
    
class NotificationSummaryAPIView(generics.ListAPIView):
    serializer_class = NotificationSummarySerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        vendor_id = self.kwargs['vendor_id']
        vendor = Vendor.objects.get(id=vendor_id)

        un_read_noti = Notification.objects.filter(vendor=vendor, seen=False).count()
        read_noti = Notification.objects.filter(vendor=vendor, seen=True).count()
        all_noti = Notification.objects.filter(vendor=vendor).count()

        return [{
            'un_read_noti': un_read_noti,
            'read_noti': read_noti,
            'all_noti': all_noti,
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    
class NotificationMarkAsSeen(generics.RetrieveUpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        vendor_id = self.kwargs['vendor_id']
        noti_id = self.kwargs['noti_id']
        vendor = Vendor.objects.get(id=vendor_id)
        notification = Notification.objects.get(vendor=vendor, id=noti_id)
        notification.seen = True
        notification.save()
        return notification
    

############################ Less Redundant Notfication Code ############################
# class NotificationAPIView(generics.ListCreateAPIView, generics.RetrieveUpdateAPIView):
#     serializer_class = NotificationSerializer
#     permission_classes = (AllowAny, )

#     def get_queryset(self):
#         vendor_id = self.kwargs['vendor_id']
#         vendor = Vendor.objects.get(id=vendor_id)
        
#         seen_param = self.request.query_params.get('seen', None)

#         if seen_param == 'true':
#             return Notification.objects.filter(vendor=vendor, seen=True).order_by('seen')
#         elif seen_param == 'false':
#             return Notification.objects.filter(vendor=vendor, seen=False).order_by('seen')
#         else:
#             return Notification.objects.filter(vendor=vendor).order_by('seen')

#     def list(self, request, *args, **kwargs):
#         if 'summary' in request.query_params:
#             return self.get_summary(request, *args, **kwargs)
#         return super().list(request, *args, **kwargs)

#     def get_summary(self, request, *args, **kwargs):
#         vendor_id = kwargs['vendor_id']
#         vendor = Vendor.objects.get(id=vendor_id)

#         un_read_noti = Notification.objects.filter(vendor=vendor, seen=False).count()
#         read_noti = Notification.objects.filter(vendor=vendor, seen=True).count()
#         all_noti = Notification.objects.filter(vendor=vendor).count()

#         return Response({
#             'un_read_noti': un_read_noti,
#             'read_noti': read_noti,
#             'all_noti': all_noti,
#         })

#     def perform_update(self, serializer):
#         serializer.instance.seen = True
#         serializer.save()

# Example URL patterns in urls.py:
# path('notifications/<int:vendor_id>/', NotificationAPIView.as_view(), name='notification-list'),
# path('notifications/<int:vendor_id>/<int:pk>/', NotificationAPIView.as_view(), name='notification-detail'),





class VendorProfileUpdateView(generics.RetrieveUpdateAPIView):
    """The URL segment is a user id (as sent by the frontend); the profile is looked up by user."""
    serializer_class = ProfileSerializer
    permission_classes = (IsStaffOwner,)
    parser_classes = (MultiPartParser, FormParser)

    def get_object(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['pk'])
        profile, _created = Profile.objects.get_or_create(user_id=user_id)
        return profile


class ShopUpdateView(generics.RetrieveUpdateAPIView):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = (IsStaffOwner,)      
    parser_classes = (MultiPartParser, FormParser)


class ShopAPIView(generics.RetrieveUpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = VendorSerializer
    permission_classes = (PublicReadStaffWrite, )

    def get_object(self):
        vendor_slug = self.kwargs['vendor_slug']

        vendor = Vendor.objects.get(slug=vendor_slug)
        return vendor
    

class ShopProductsAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)  # public storefront listing

    def get_queryset(self):
        vendor_slug = self.kwargs['vendor_slug']
        vendor = Vendor.objects.get(slug=vendor_slug)
        products = Product.objects.filter(vendor=vendor)
        return products
    
class VendorRegister(generics.CreateAPIView):
    serializer_class = VendorSerializer
    queryset = Vendor.objects.all()
    permission_classes = (IsStaffOwner,)

    def create(self, request, *args, **kwargs):
        payload = request.data

        image = payload['image']
        name = payload['name']
        email = payload['email']
        description = payload['description']
        mobile = payload['mobile']

        # The shop is always attached to the signed-in staff user; a user_id in the body is ignored.
        Vendor.objects.create(
            image=image,
            name=name,
            email=email,
            description=description,
            mobile=mobile,
            user=request.user,
        )

        return Response({"message":"Created vendor account"})
    

class CourierListAPIView(generics.ListAPIView):
    queryset = DeliveryCouriers.objects.all()
    serializer_class = DeliveryCouriersSerializer
    permission_classes = (IsStaffOwner,)

    

class OrderItemDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = CartOrderItemSerializer
    permission_classes = (IsStaffOwner,)
    queryset = CartOrderItem.objects.all()

    def get_object(self):
        pk = self.kwargs['pk']
        return CartOrderItem.objects.get(id=pk)
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.tracking_id = request.data.get('tracking_id', instance.tracking_id)

        delivery_couriers_id = request.data.get('delivery_couriers')
        delivery_couriers = DeliveryCouriers.objects.get(id=delivery_couriers_id)
        instance.delivery_couriers = delivery_couriers

        

        notify_buyer = request.data.get('notify_buyer')
        if notify_buyer == 'true':
            merge_data = {
                'instance': instance, 
                'tracking_id': instance.tracking_id, 
                'delivery_couriers': instance.delivery_couriers.name, 
                'tracking_link': f"{instance.delivery_couriers.tracking_website}?{instance.delivery_couriers.url_parameter}={instance.tracking_id}", 
            }
            subject = f"Tracking ID Added for {instance.product.title}"
            text_body = render_to_string("email/tracking_id_added.txt", merge_data)
            html_body = render_to_string("email/tracking_id_added.html", merge_data)
            
            msg = EmailMultiAlternatives(
                subject=subject, from_email=settings.FROM_EMAIL,
                to=[instance.order.email], body=text_body
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()

        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)