from django.db import models

# Create your models here.
from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from django.utils import timezone
from django.template.defaultfilters import escape
from django.urls import reverse
from django.shortcuts import redirect
from django.dispatch import receiver
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver


from userauths.models import User, user_directory_path, Profile
from vendor.models import Vendor
from core.models import AppendOnlyModel
from store.money_mirror import MoneyMirrorMixin

import shortuuid
import datetime
import os 




DISCOUNT_TYPE = (
    ("Percentage", "Percentage"),
    ("Flat Rate", "Flat Rate"),
)

COUPON_KIND_PERCENT = "PERCENT"
COUPON_KIND_FLAT = "FLAT"
COUPON_KIND_CHOICES = (
    (COUPON_KIND_PERCENT, "Percentage off"),
    (COUPON_KIND_FLAT, "Flat rupees off"),
)

STATUS_CHOICE = (
    ("processing", "Processing"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
)


STATUS = (
    ("draft", "Draft"),
    ("disabled", "Disabled"),
    ("rejected", "Rejected"),
    ("in_review", "In Review"),
    ("published", "Published"),
)


PAYMENT_METHOD_CHOICES = (
    ("UPI", "UPI"),
    ("CARD", "Card"),
    ("NETBANKING", "Netbanking"),
    ("WALLET", "Wallet"),
    ("COD", "Cash on Delivery"),
)

ORDER_CHANNEL_CHOICES = (
    ("WEBSITE", "Website"),
    ("AMAZON", "Amazon"),
    ("FLIPKART", "Flipkart"),
    ("QCOMM", "Quick commerce"),
    ("OFFLINE", "Offline"),
    ("MANUAL", "Manual"),
)

PAYMENT_STATUS = (
    ("paid", "Paid"),
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("cancelled", "Cancelled"),
    ("initiated", 'Initiated'),
    ("failed", 'failed'),
    ("refunding", 'refunding'),
    ("refunded", 'refunded'),
    ("unpaid", 'unpaid'),
    ("expired", 'expired'),
)


ORDER_STATUS = (
    ("Pending", "Pending"),
    ("Fulfilled", "Fulfilled"),
    ("Partially Fulfilled", "Partially Fulfilled"),
    ("Cancelled", "Cancelled"),
    
)

AUCTION_STATUS = (
    ("on_going", "On Going"),
    ("finished", "finished"),
    ("cancelled", "cancelled")
)

WIN_STATUS = (
    ("won", "Won"),
    ("lost", "Lost"),
    ("pending", "pending")
)

PRODUCT_TYPE = (
    ("regular", "Regular"),
    ("auction", "Auction"),
    ("offer", "Offer")
)

OFFER_STATUS = (
    ("accepted", "Accepted"),
    ("rejected", "Rejected"),
    ("pending", "Pending"),
)

PRODUCT_CONDITION = (
    ("new", "New"),
    ("old_2nd_hand", "“Used or 2nd Hand"),
    ("custom", "Custom"),
)

PRODUCT_CONDITION_RATING = (
    (1, "1/10"),
    (2, "2/10"),
    (3, "3/10"),
    (4, "4/10"),
    (5, "5/10"),
    (6, "6/10"),
    (7, "7/10"),
    (8, "8/10"),
    (9, "9/10"),
    (10,"10/10"),
)


DELIVERY_STATUS = (
    ("On Hold", "On Hold"),
    ("Shipping Processing", "Shipping Processing"),
    ("Shipped", "Shipped"),
    ("Arrived", "Arrived"),
    ("Delivered", "Delivered"),
    ("Returning", 'Returning'),
    ("Returned", 'Returned'),
)

PAYMENT_METHOD = (
    ("Paypal", "Paypal"),
    ("Credit/Debit Card", "Credit/Debit Card"),
    ("Wallet Points", "Wallet Points"),
    
)



REVIEW_PENDING = "PENDING"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"
REVIEW_STATUS_CHOICES = (
    (REVIEW_PENDING, "Pending moderation"),
    (REVIEW_APPROVED, "Approved"),
    (REVIEW_REJECTED, "Rejected"),
)

RATING = (
    ( 1,  "★☆☆☆☆"),
    ( 2,  "★★☆☆☆"),
    ( 3,  "★★★☆☆"),
    ( 4,  "★★★★☆"),
    ( 5,  "★★★★★"),
)


# Model for Product Categories
class Category(models.Model):
    # Category title
    title = models.CharField(max_length=100)
    # Image for the category
    image = models.ImageField(upload_to=user_directory_path, default="category.jpg", null=True, blank=True)
    # Is the category active?
    active = models.BooleanField(default=True)
    # Slug for SEO-friendly URLs
    slug = models.SlugField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    # Returns an HTML image tag for the category's image
    def thumbnail(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.title
    
    # Returns the count of products in this category
    def product_count(self):
        product_count = Product.objects.filter(category=self).count()
        return product_count
    
    # Returns the products in this category
    def cat_products(self):
        cat_products = Product.objects.filter(category=self)
        return cat_products

    # Custom save method to generate a slug if it's empty
    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + str(uniqueid.lower())
        super(Category, self).save(*args, **kwargs) 


# Model for Tags
class Tag(models.Model):
    # Tag title
    title = models.CharField(max_length=30)
    # Category associated with the tag
    category = models.ForeignKey(Category, default="", verbose_name="Category", on_delete=models.PROTECT)
    # Is the tag active?
    active = models.BooleanField(default=True)
    # Unique slug for SEO-friendly URLs
    slug = models.SlugField("Tag slug", max_length=30, null=False, blank=False, unique=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = "Tags"
        ordering = ('title',)

# Model for Brands
class Brand(models.Model):
    # Brand title
    title = models.CharField(max_length=100)
    # Image for the brand
    image = models.ImageField(upload_to=user_directory_path, default="brand.jpg", null=True, blank=True)
    # Is the brand active?
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Brands"

    # Returns an HTML image tag for the brand's image
    def brand_image(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.title

# Model for Products
class Product(models.Model):
    # Product title
    title = models.CharField(max_length=100)
    # Image for the product
    image = models.FileField(upload_to=user_directory_path, blank=True, null=True, default="product.jpg")
    # Description for the product using HTML
    description = models.TextField(null=True, blank=True)
    
    # Categories that the product belongs to
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="category")
    # Tags associated with the product
    tags = models.CharField(max_length=1000, null=True, blank=True)
    # Brand associated with the product
    brand = models.CharField(max_length=100, null=True, blank=True)

    # Price and other financial details
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    old_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Stock quantity and availability status
    stock_qty = models.PositiveIntegerField(default=0)
    in_stock = models.BooleanField(default=True)
    
    # Product status and type
    status = models.CharField(choices=STATUS, max_length=50, default="published", null=True, blank=True)
    type = models.CharField(choices=PRODUCT_TYPE, max_length=50, default="regular")
    
    # Product flags (featured, hot deal, special offer, digital)
    featured = models.BooleanField(default=False)
    hot_deal = models.BooleanField(default=False)
    special_offer = models.BooleanField(default=False)
    digital = models.BooleanField(default=False)
    
    # Product statistics (views, orders, saved, rating)
    views = models.PositiveIntegerField(default=0, null=True, blank=True)
    orders = models.PositiveIntegerField(default=0, null=True, blank=True)
    saved = models.PositiveIntegerField(default=0, null=True, blank=True)
    rating = models.IntegerField(default=0, null=True, blank=True)
    
    # Vendor associated with the product
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendor")
    
    # Unique short UUIDs for SKU and product
    sku = ShortUUIDField(unique=True, length=5, max_length=50, prefix="SKU", alphabet="1234567890")
    pid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    
    # Slug for SEO-friendly URLs
    slug = models.SlugField(null=True, blank=True)
    
    # Date of product creation
    date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Products"

    # Returns an HTML image tag for the product's image
    def product_image(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.title
    
    # Returns the count of products in the same category as this product
    def category_count(self):
        return Product.objects.filter(category__in=self.category).count()

    # Calculates the discount percentage between old and new prices
    def get_precentage(self):
        """
        How far below the MRP this product is, as a whole percent.

        A product with no MRP (or an MRP at or below the price) is not discounted, so the answer
        is 0. Before this it divided by zero and took the whole listing page down with it.
        """
        old_price = self.old_price or 0
        price = self.price or 0
        if old_price <= 0 or old_price <= price:
            return 0
        return round(((old_price - price) / old_price) * 100, 0)
    
    # Average rating of the product. Only reviews the owner has approved count (Phase G4).
    #
    # A view that lists many products can work these three out for the whole page in one query
    # (see store.views.CatalogueListMixin) and attach the answers as `_rating_avg`,
    # `_rating_count` and `_order_count`; each method uses that when it is there. On its own a
    # product still asks for its own numbers, so nothing else has to change.
    def product_rating(self):
        annotated = getattr(self, "_rating_avg", None)
        if annotated is not None or hasattr(self, "_rating_avg"):
            return annotated
        return Review.objects.filter(product=self, status=REVIEW_APPROVED).aggregate(
            avg_rating=models.Avg('rating'))['avg_rating']
    
    # Number of approved reviews for the product
    def rating_count(self):
        annotated = getattr(self, "_rating_count", None)
        if annotated is not None:
            return annotated
        return Review.objects.filter(product=self, status=REVIEW_APPROVED).count()
    
    # Returns the count of orders for the product with "paid" payment status
    def order_count(self):
        annotated = getattr(self, "_order_count", None)
        if annotated is not None:
            return annotated
        return CartOrderItem.objects.filter(product=self, order__payment_status="paid").count()

    # Returns the gallery images linked to this product
    # These four return the product's own rows. They go through the reverse relation (rather
    # than a fresh query against the table) so that a view which has prefetched them serves a
    # whole page without asking the database once per product.
    def gallery(self):
        return self.gallery_set.all()
    
    # def specification(self):
    #     return Specification.objects.filter(product=self)

    def specification(self):
        return self.specification_set.all()


    def color(self):
        return self.color_set.all()
    
    def size(self):
        return self.size_set.all()

    # Returns a list of products frequently bought together with this product
    def frequently_bought_together(self):
        frequently_bought_together_products = Product.objects.filter(order_item__order__in=CartOrder.objects.filter(orderitem__product=self)).exclude(id=self.id).annotate(count=models.Count('id')).order_by('-id')[:3]
        return frequently_bought_together_products
    
    # Custom save method to generate a slug if it's empty, update in_stock, and calculate the product rating
    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.title) + "-" + str(uniqueid.lower())
        
        if self.stock_qty is not None:
            if self.stock_qty == 0:
                self.in_stock = False
                
            if self.stock_qty > 0:
                self.in_stock = True
        else:
            self.stock_qty = 0
            self.in_stock = False
        
        self.rating = self.product_rating()
            
        super(Product, self).save(*args, **kwargs) 


# Model for Product Gallery
class Gallery(models.Model):
    # Product associated with the gallery
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
    # Image for the gallery
    image = models.FileField(upload_to=user_directory_path, default="gallery.jpg")
    # Is the image active?
    active = models.BooleanField(default=True)
    # Date of gallery image creation
    date = models.DateTimeField(auto_now_add=True)
    # Unique short UUID for gallery image
    gid = ShortUUIDField(length=10, max_length=25, alphabet="abcdefghijklmnopqrstuvxyz")

    class Meta:
        ordering = ["date"]
        verbose_name_plural = "Product Images"

    def __str__(self):
        return "Image"

# Model for Product Specifications
class Specification(models.Model):
    # Product associated with the specification
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
    # Specification title
    title = models.CharField(max_length=100, blank=True, null=True)
    # Specification content
    content = models.CharField(max_length=1000, blank=True, null=True)

# Model for Product Sizes
class Size(models.Model):
    # Product associated with the size
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
    # Size name
    name = models.CharField(max_length=100, blank=True, null=True)
    # Price for the size
    price = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)

# Model for Product Colors
class Color(models.Model):
    # Product associated with the color
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
    # Color name
    name = models.CharField(max_length=100, blank=True, null=True)
    # Color code (if applicable)
    color_code = models.CharField(max_length=100, blank=True, null=True)
    # Image for the color
    image = models.FileField(upload_to=user_directory_path, blank=True, null=True)

# Model for Product FAQs
class ProductFaq(models.Model):
    # User who asked the FAQ
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    # Unique short UUID for FAQ
    pid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    # Product associated with the FAQ
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, related_name="product_faq")
    # Email of the user who asked the question
    email = models.EmailField()
    # FAQ question
    question = models.CharField(max_length=1000)
    # FAQ answer
    answer = models.CharField(max_length=10000, null=True, blank=True)
    # Is the FAQ active?
    active = models.BooleanField(default=False)
    # Date of FAQ creation
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Product Faqs"
        ordering = ["-date"]
        
    def __str__(self):
        return self.question
    
class Cart(MoneyMirrorMixin, models.Model):
    # Legacy Decimal column -> `<name>_paise` twin. Paise is the truth (see store/money_mirror.py).
    MONEY_FIELDS = ("price", "sub_total", "shipping_amount", "service_fee", "tax_fee", "total")

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    qty = models.PositiveIntegerField(default=0, null=True, blank=True)
    price = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    sub_total = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    shipping_amount = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    service_fee = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    tax_fee = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    total = models.DecimalField(decimal_places=2, max_digits=12, default=0.00, null=True, blank=True)
    # --- integer paise twins (Phase G1). Unit price and line subtotal are a snapshot taken when
    # the line was last written; cart totals are always recomputed by store.pricing.quote().
    price_paise = models.BigIntegerField(default=0)
    sub_total_paise = models.BigIntegerField(default=0)
    shipping_amount_paise = models.BigIntegerField(default=0)
    service_fee_paise = models.BigIntegerField(default=0)
    tax_fee_paise = models.BigIntegerField(default=0)
    total_paise = models.BigIntegerField(default=0)
    country = models.CharField(max_length=100, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    color = models.CharField(max_length=100, null=True, blank=True)
    cart_id = models.CharField(max_length=1000, null=True, blank=True)
    # The exact sellable unit in the cart. Null only on rows created before variants existed.
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_items")
    # Last time this line was touched: drives abandoned-cart detection (Feature 4).
    updated_at = models.DateTimeField(auto_now=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.cart_id} - {self.product.title}'



# Model for Cart Orders
class CartOrder(MoneyMirrorMixin, models.Model):
    # Legacy Decimal column -> `<name>_paise` twin. Paise is the truth (see store/money_mirror.py).
    #   sub_total        item subtotal before discount
    #   saved            order-level coupon discount
    #   shipping_amount  flat shipping, 0 when free
    #   tax_fee          tax carved out of the tax-inclusive total (0 while tax_rate_bps is 0)
    #   service_fee      always 0 from G1 on (the marketplace fee is no longer charged)
    #   initial_total    sub_total + shipping_amount, i.e. the total before the discount
    #   total            sub_total - saved + shipping_amount: what the customer pays
    MONEY_FIELDS = ("sub_total", "shipping_amount", "tax_fee", "service_fee", "total", "initial_total", "saved")

    # Vendors associated with the order
    vendor = models.ManyToManyField(Vendor, blank=True)
    # Buyer of the order
    buyer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="buyer", blank=True)
    # Total price of the order
    sub_total = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    # Shipping cost
    shipping_amount = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    # VAT (Value Added Tax) cost
    tax_fee = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    # Service fee cost
    service_fee = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    # Total cost of the order
    total = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)

    # Order status attributes
    payment_status = models.CharField(max_length=100, choices=PAYMENT_STATUS, default="initiated")
    order_status = models.CharField(max_length=100, choices=ORDER_STATUS, default="Pending")
    
    
    # Discounts
    initial_total = models.DecimalField(default=0.00, max_digits=12, decimal_places=2, help_text="The original total before discounts")
    saved = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True, help_text="Amount saved by customer")

    # --- integer paise twins (Phase G1): the stored snapshot of store.pricing.quote() ----------
    sub_total_paise = models.BigIntegerField(default=0)
    shipping_amount_paise = models.BigIntegerField(default=0)
    tax_fee_paise = models.BigIntegerField(default=0)
    service_fee_paise = models.BigIntegerField(default=0)
    total_paise = models.BigIntegerField(default=0)
    initial_total_paise = models.BigIntegerField(default=0)
    saved_paise = models.BigIntegerField(default=0)
    # Code of the coupon currently applied to this order (snapshot text; blank when none).
    coupon_code = models.CharField(max_length=1000, blank=True, default="")
    
    # Personal Informations
    full_name = models.CharField(max_length=1000)
    email = models.CharField(max_length=1000)
    mobile = models.CharField(max_length=1000)
    
     # Shipping Address
    address = models.CharField(max_length=1000, null=True, blank=True)
    city = models.CharField(max_length=1000, null=True, blank=True)
    state = models.CharField(max_length=1000, null=True, blank=True)
    country = models.CharField(max_length=1000, null=True, blank=True)

    coupons = models.ManyToManyField('store.Coupon', blank=True)
    
    stripe_session_id = models.CharField(max_length=200,null=True, blank=True)
    # --- single-brand D2C additions (Phase F-B) ---------------------------------
    # How the customer is paying. Blank on legacy rows.
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, default="")
    # Which sales channel produced this order. Business logic must not assume WEBSITE.
    channel = models.CharField(max_length=20, choices=ORDER_CHANNEL_CHOICES, default="WEBSITE")
    # Delivery pincode, kept separate from the free-text address for RTO analysis by area.
    pincode = models.CharField(max_length=10, blank=True, default="")
    # Customer phone in E.164 (+91XXXXXXXXXX) for WhatsApp and SMS. Derived from `mobile`.
    phone_e164 = models.CharField(max_length=20, blank=True, default="")
    # One order draft per checkout attempt: re-POSTing the same cart returns the same order.
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    # --- payments and COD (Phase G3) ----------------------------------------------------------
    # Which provider this order is being (or was) paid through: "razorpay", "cod", "stripe", "paypal".
    payment_provider = models.CharField(max_length=20, blank=True, default="")
    # Razorpay's ids for this order (field names as in Razorpay's documentation).
    razorpay_order_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True, default="")
    # Set when the owner has confirmed a Cash on Delivery order with the customer.
    cod_confirmed_at = models.DateTimeField(null=True, blank=True)
    cod_confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # Non-empty when the owner must act on this order (for example: paid, but stock is gone, so
    # a refund is due). Shown on the owner's order screens. Cleared by the owner.
    needs_attention = models.CharField(max_length=255, blank=True, default="")
    # When every line of the order was delivered (drives the review-request email).
    delivered_at = models.DateTimeField(null=True, blank=True)
    oid = ShortUUIDField(length=10, max_length=25, alphabet="abcdefghijklmnopqrstuvxyz", unique=True)
    date = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Cart Order"

    def __str__(self):
        return self.oid

    def get_order_items(self):
        return CartOrderItem.objects.filter(order=self)
    

# Define a model for Cart Order Item
class CartOrderItem(MoneyMirrorMixin, models.Model):
    # Legacy Decimal column -> `<name>_paise` twin. Paise is the truth (see store/money_mirror.py).
    #   price            unit price snapshot
    #   sub_total        price x qty, before discount
    #   saved            this line's share of the order discount
    #   shipping_amount  always 0 from G1 on (shipping is charged once per order)
    #   tax_fee          tax carved out of this line's tax-inclusive total
    #   service_fee      always 0 from G1 on
    #   initial_total    line total before discount (= sub_total)
    #   total            sub_total - saved
    MONEY_FIELDS = ("price", "sub_total", "shipping_amount", "tax_fee", "service_fee", "total", "initial_total", "saved")

    # A foreign key relationship to the CartOrder model with CASCADE deletion
    order = models.ForeignKey(CartOrder, on_delete=models.CASCADE, related_name="orderitem")
    # A foreign key relationship to the Product model with CASCADE deletion
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="order_item")
    # The exact sellable unit ordered. Null on legacy rows created before variants existed.
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, null=True, blank=True, related_name="order_items")
    # Integer field to store the quantity (default is 0)
    qty = models.IntegerField(default=0)
    # Fields for color and size with max length 100, allowing null and blank values
    color = models.CharField(max_length=100, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    # Decimal fields for price, total, shipping, VAT, service fee, grand total, and more
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Total of Product price * Product Qty")
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Estimated Shipping Fee = shipping_fee * total")
    tax_fee = models.DecimalField(default=0.00, max_digits=12, decimal_places=2, help_text="Estimated Vat based on delivery country = tax_rate * (total + shipping)")
    service_fee = models.DecimalField(default=0.00, max_digits=12, decimal_places=2, help_text="Estimated Service Fee = service_fee * total (paid by buyer to platform)")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Grand Total of all amount listed above")
    
    expected_delivery_date_from = models.DateField(auto_now_add=False, null=True, blank=True)
    expected_delivery_date_to = models.DateField(auto_now_add=False, null=True, blank=True)


    initial_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Grand Total of all amount listed above before discount")
    saved = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True, help_text="Amount saved by customer")

    # --- integer paise twins (Phase G1) -------------------------------------------------------
    price_paise = models.BigIntegerField(default=0)
    sub_total_paise = models.BigIntegerField(default=0)
    shipping_amount_paise = models.BigIntegerField(default=0)
    tax_fee_paise = models.BigIntegerField(default=0)
    service_fee_paise = models.BigIntegerField(default=0)
    total_paise = models.BigIntegerField(default=0)
    initial_total_paise = models.BigIntegerField(default=0)
    saved_paise = models.BigIntegerField(default=0)
    
    # Order stages
    order_placed = models.BooleanField(default=False)
    processing_order = models.BooleanField(default=False)
    quality_check = models.BooleanField(default=False)
    product_shipped = models.BooleanField(default=False)
    product_arrived = models.BooleanField(default=False)
    product_delivered = models.BooleanField(default=False)

    # Various fields for delivery status, delivery couriers, tracking ID, coupons, and more
    delivery_status = models.CharField(max_length=100, choices=DELIVERY_STATUS, default="On Hold")
    delivery_couriers = models.ForeignKey("store.DeliveryCouriers", on_delete=models.SET_NULL, null=True, blank=True)
    tracking_id = models.CharField(max_length=100000, null=True, blank=True)
    
    coupon = models.ManyToManyField("store.Coupon", blank=True)
    applied_coupon = models.BooleanField(default=False)
    oid = ShortUUIDField(length=10, max_length=25, alphabet="abcdefghijklmnopqrstuvxyz")
    # A foreign key relationship to the Vendor model with SET_NULL option
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(default=timezone.now)
    
    class Meta:
        verbose_name_plural = "Cart Order Item"
        ordering = ["-date"]
        
    # Method to generate an HTML image tag for the order item
    def order_img(self):
        return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.product.image.url))
   
    # Method to return a formatted order ID
    def order_id(self):
        return f"Order ID #{self.order.oid}"
    
    # Method to return a string representation of the object
    def __str__(self):
        return self.oid

# Define a model for Reviews
class Review(models.Model):
    # A foreign key relationship to the User model with SET_NULL option, allowing null and blank values
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    # A foreign key relationship to the Product model with SET_NULL option, allowing null and blank values, and specifying a related name
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviews")
    # Text field for the review content
    review = models.TextField()
    # Field for a reply with max length 1000, allowing null and blank values
    reply = models.CharField(null=True, blank=True, max_length=1000)
    # Integer field for rating with predefined choices
    rating = models.IntegerField(choices=RATING, default=None)
    # Boolean field for the active status
    active = models.BooleanField(default=False)
    # Many-to-many relationships with User model for helpful and not helpful actions
    helpful = models.ManyToManyField(User, blank=True, related_name="helpful")
    not_helpful = models.ManyToManyField(User, blank=True, related_name="not_helpful")
    # Date and time field
    date = models.DateTimeField(auto_now_add=True)
    # --- verified purchase and moderation (Phase G4) ------------------------------------------
    # The delivered order line that entitles this customer to review the product.
    order_item = models.ForeignKey("store.CartOrderItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    # New reviews start PENDING and are public only once the owner approves them.
    status = models.CharField(max_length=10, choices=REVIEW_STATUS_CHOICES, default=REVIEW_PENDING, db_index=True)
    moderated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    moderated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Reviews & Rating"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(user__isnull=False, product__isnull=False),
                name="store_review_one_per_user_per_product",
            ),
        ]
        
    # Method to return a string representation of the object
    def __str__(self):
        if self.product:
            return self.product.title
        else:
            return "Review"
        
    # Method to get the rating value
    def get_rating(self):
        return self.rating
    
    def profile(self):
        return Profile.objects.get(user=self.user)

    def save(self, *args, **kwargs):
        # The legacy `active` flag mirrors the moderation status so older screens stay correct.
        self.active = self.status == REVIEW_APPROVED
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields and "active" not in update_fields:
            kwargs["update_fields"] = list(update_fields) + ["active"]
        super().save(*args, **kwargs)
    
# Signal handler to update the product rating when a review is saved
@receiver(post_save, sender=Review)
def update_product_rating(sender, instance, **kwargs):
    if instance.product:
        instance.product.save()

# Define a model for Wishlist
class Wishlist(models.Model):
    # A foreign key relationship to the User model with CASCADE deletion
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    # A foreign key relationship to the Product model with CASCADE deletion, specifying a related name
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist")
    # Date and time field
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Wishlist"
    
    # Method to return a string representation of the object
    def __str__(self):
        if self.product.title:
            return self.product.title
        else:
            return "Wishlist"
        
# Define a model for Notification
class Notification(models.Model):
    # A foreign key relationship to the User model with CASCADE deletion
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # A foreign key relationship to the Vendor model with CASCADE deletion
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    # A foreign key relationship to the CartOrder model with CASCADE deletion, specifying a related name
    order = models.ForeignKey(CartOrder, on_delete=models.SET_NULL, null=True, blank=True)
    # A foreign key relationship to the CartOrderItem model with CASCADE deletion, specifying a related name
    order_item = models.ForeignKey(CartOrderItem, on_delete=models.SET_NULL, null=True, blank=True)
    # Is read Boolean Field
    seen = models.BooleanField(default=False)
    # Date and time field
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Notification"
    
    # Method to return a string representation of the object
    def __str__(self):
        if self.order:
            return self.order.oid
        else:
            return "Notification"

# Define a model for Address
class Address(models.Model):
    # A foreign key relationship to the User model with CASCADE deletion
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    # Fields for full name, mobile, email, country, state, town/city, address, zip code, and status
    full_name = models.CharField(max_length=200)
    mobile = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    country = models.ForeignKey("addon.Tax", on_delete=models.SET_NULL, null=True, related_name="address_country", blank=True)
    state = models.CharField(max_length=100)
    town_city = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    zip = models.CharField(max_length=100)
    status = models.BooleanField(default=False)
    same_as_billing_address = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Address"
    
    # Method to return a string representation of the object
    def __str__(self):
        if self.user:
            return self.user.username
        else:
            return "Address"

# Define a model for Cancelled Order
class CancelledOrder(models.Model):
    # A foreign key relationship to the User model with CASCADE deletion
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    # A foreign key relationship to the CartOrderItem model with SET_NULL option, allowing null values
    orderitem = models.ForeignKey("store.CartOrderItem", on_delete=models.SET_NULL, null=True)
    # Field for email with max length 100
    email = models.CharField(max_length=100)
    # Boolean field for the refunded status
    refunded = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Cancelled Order"
    
    # Method to return a string representation of the object
    def __str__(self):
        if self.user:
            return str(self.user.username)
        else:
            return "Cancelled Order"

# Define a model for Coupon
class Coupon(models.Model):
    # A foreign key relationship to the Vendor model with SET_NULL option, allowing null values, and specifying a related name
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, related_name="coupon_vendor")
    # Many-to-many relationship with User model for users who used the coupon
    used_by = models.ManyToManyField(User, blank=True)
    # Fields for code, type, discount, redemption, date, and more
    code = models.CharField(max_length=1000)
    # type = models.CharField(max_length=100, choices=DISCOUNT_TYPE, default="Percentage")
    discount = models.IntegerField(default=1, validators=[MinValueValidator(0), MaxValueValidator(100)])
    # redemption = models.IntegerField(default=0)
    date = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    # make_public = models.BooleanField(default=False)
    # valid_from = models.DateField()
    # valid_to = models.DateField()
    # ShortUUID field
    cid = ShortUUIDField(length=10, max_length=25, alphabet="abcdefghijklmnopqrstuvxyz")

    # --- coupon rules (Phase G1) ---------------------------------------------------------------
    # PERCENT uses the existing `discount` integer as the percentage. FLAT uses `flat_off_paise`.
    kind = models.CharField(max_length=10, choices=COUPON_KIND_CHOICES, default=COUPON_KIND_PERCENT)
    flat_off_paise = models.BigIntegerField(default=0, validators=[MinValueValidator(0)], help_text="FLAT coupons only: amount off, in paise (Rs 100 = 10000).")
    min_order_paise = models.BigIntegerField(default=0, validators=[MinValueValidator(0)], help_text="Minimum item subtotal, in paise, before this coupon applies. 0 = no minimum.")
    max_total_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Total number of orders that may use this coupon. Empty = unlimited.")
    max_uses_per_customer = models.PositiveIntegerField(default=1, help_text="How many orders one customer may use this coupon on.")
    valid_from = models.DateTimeField(null=True, blank=True, help_text="Empty = valid immediately.")
    valid_until = models.DateTimeField(null=True, blank=True, help_text="Empty = never expires.")
    
    # Method to calculate and save the percentage discount
    def save(self, *args, **kwargs):
        new_discount = int(self.discount) / 100
        self.get_percent = new_discount
        super(Coupon, self).save(*args, **kwargs) 
    
    # Method to return a string representation of the object
    def __str__(self):
        return self.code
    
    class Meta:
        ordering =['-id']

class CouponRedemption(AppendOnlyModel):
    """
    One use of a coupon on one order. Append-only, unique per (coupon, order).

    Written in the same transaction that puts the discount on the order, with the coupon row
    locked. A redemption only counts towards the coupon's caps while its order is alive and
    still carries this coupon (see store.pricing.live_redemptions), so cancelling an order, or
    removing the coupon from it, frees the use without deleting this row.
    `discount_paise` is the discount at the moment of redemption; the order's `saved_paise`
    is the authoritative current value.
    """

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order = models.ForeignKey(CartOrder, on_delete=models.CASCADE, related_name="coupon_redemptions")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="coupon_redemptions")
    email = models.CharField(max_length=254, blank=True, default="")
    phone_e164 = models.CharField(max_length=20, blank=True, default="")
    discount_paise = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["coupon", "order"], name="store_couponredemption_coupon_order_uniq"),
        ]
        indexes = [models.Index(fields=["coupon", "email"]), models.Index(fields=["coupon", "phone_e164"])]

    def __str__(self):
        return f"{self.coupon.code} on {self.order.oid}"


# Define a model for Coupon Users
class CouponUsers(models.Model):
    # A foreign key relationship to the Coupon model with CASCADE deletion
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    # A foreign key relationship to the CartOrder model with CASCADE deletion
    order = models.ForeignKey(CartOrder, on_delete=models.CASCADE)
    # Fields for full name, email, and mobile
    full_name = models.CharField(max_length=1000)
    email = models.CharField(max_length=1000)
    mobile = models.CharField(max_length=1000)
    
    # Method to return a string representation of the coupon code
    def __str__(self):
        return str(self.coupon.code)
    
    class Meta:
        ordering =['-id']

# Define a model for Delivery Couriers
class DeliveryCouriers(models.Model):
    name = models.CharField(max_length=1000, null=True, blank=True)
    tracking_website = models.URLField(null=True, blank=True)
    url_parameter = models.CharField(null=True, blank=True, max_length=100)
    
    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Delivery Couriers"
    
    def __str__(self):
        return self.name