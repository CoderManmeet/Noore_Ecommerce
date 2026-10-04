from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from store.models import CancelledOrder, Cart, CartOrderItem, Notification, CouponUsers, Product, Tag ,Category, DeliveryCouriers, CartOrder, Gallery, Brand, ProductFaq, Review,  Specification, Coupon, Color, Size, Address, Wishlist, Vendor
from addon.models import ConfigSettings
from store.models import Gallery
from catalog.models import ProductVariant
from core.serializers import PublicUserSerializer, SafeDepthModelSerializer
from userauths.serializer import PublicProfileSerializer

class ConfigSettingsSerializer(SafeDepthModelSerializer):

    class Meta:
            model = ConfigSettings
            fields = '__all__'


# Define a serializer for the Category model
class CategorySerializer(SafeDepthModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

# Define a serializer for the Tag model
class TagSerializer(SafeDepthModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'

# Define a serializer for the Brand model
class BrandSerializer(SafeDepthModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


        # Define a serializer for the Gallery model
class GallerySerializer(SafeDepthModelSerializer):
    # Serialize the related Product model

    class Meta:
        model = Gallery
        fields = '__all__'

# Define a serializer for the Specification model
class SpecificationSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Specification
        fields = '__all__'

# Define a serializer for the Size model
class SizeSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Size
        fields = '__all__'

# Define a serializer for the Color model
class ColorSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Color
        fields = '__all__'


# Define a serializer for the Product model
class ProductVariantSerializer(SafeDepthModelSerializer):
    """Public view of a sellable unit, including live availability from the stock ledger."""

    available_qty = serializers.IntegerField(read_only=True)
    price = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    best_before = serializers.SerializerMethodField()
    # G2: what the storefront may honestly show. `stock` is {state, label, left};
    # `strikethrough` is {compare_at_paise, percent_off, basis} or null.
    stock = serializers.SerializerMethodField()
    strikethrough = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ["id", "sku", "name", "size", "color", "options", "weight_grams", "price_paise", "price",
                  "mrp_paise", "mrp", "perishable", "is_default", "active", "available_qty", "stock",
                  "strikethrough", "best_before"]
        read_only_fields = fields

    def get_stock(self, obj):
        from catalog.display import stock_status

        return stock_status(obj)

    def get_strikethrough(self, obj):
        from catalog.display import strikethrough_for

        return strikethrough_for(obj)

    def get_price(self, obj):
        from core.money import from_paise

        return str(from_paise(obj.price_paise))

    def get_mrp(self, obj):
        from core.money import from_paise

        return str(from_paise(obj.mrp_paise)) if obj.mrp_paise else None

    def get_best_before(self, obj):
        """
        Earliest best-before a shopper could receive, shown only for perishable goods
        (Feature 5). Non-perishable variants return null.
        """
        if not obj.perishable:
            return None
        from inventory.services import allocatable_batches

        batches = allocatable_batches(obj)
        if not batches:
            return None
        dates = [batch.best_before for batch, _free in batches if batch.best_before]
        return min(dates).isoformat() if dates else None


class ProductSerializer(SafeDepthModelSerializer):
    # Serialize related Category, Tag, and Brand models
    # category = CategorySerializer(many=True, read_only=True)
    # tags = TagSerializer(many=True, read_only=True)
    gallery = GallerySerializer(many=True, read_only=True)
    color = ColorSerializer(many=True, read_only=True)
    size = SizeSerializer(many=True, read_only=True)
    specification = SpecificationSerializer(many=True, read_only=True)
    # Sellable units a shopper can pick: active variants only, default first.
    variants = serializers.SerializerMethodField()
    # Units available to buy across all active variants, from the stock ledger. The legacy
    # `stock_qty` column is stale and is kept in the payload for backwards compatibility only.
    available_qty = serializers.SerializerMethodField()
    # Lowest selling price among the active variants, in paise ("From Rs X" on listings).
    price_from_paise = serializers.SerializerMethodField()
    # rating = serializers.IntegerField(required=False)
    
    # specification = SpecificationSerializer(many=True, required=False)
    # color = ColorSerializer(many=True, required=False)
    # size = SizeSerializer(many=True, required=False)
    # gallery = GallerySerializer(many=True, required=False, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "image",
            "description",
            "category",
            "tags",
            "brand",
            "price",
            "old_price",
            "shipping_amount",
            "stock_qty",
            "in_stock",
            "status",
            "type",
            "featured",
            "hot_deal",
            "special_offer",
            "digital",
            "views",
            "orders",
            "saved",
            # "rating",
            "vendor",
            "sku",
            "pid",
            "slug",
            "date",
            "gallery",
            "specification",
            "size",
            "color",
            "variants",
            "available_qty",
            "price_from_paise",
            "product_rating",
            "rating_count",
            'order_count',
            "get_precentage",
        ]
    
    def __init__(self, *args, **kwargs):
        super(ProductSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new product, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

    def _active_variants(self, obj):
        cached = getattr(obj, "_active_variants_cache", None)
        if cached is None:
            cached = list(obj.variants.filter(active=True).order_by("-is_default", "price_paise", "id"))
            obj._active_variants_cache = cached
        return cached

    def get_variants(self, obj):
        return ProductVariantSerializer(self._active_variants(obj), many=True, context=self.context).data

    def get_available_qty(self, obj):
        from inventory.services import available_qty

        return sum(available_qty(variant) for variant in self._active_variants(obj))

    def get_price_from_paise(self, obj):
        prices = [variant.price_paise for variant in self._active_variants(obj)]
        return min(prices) if prices else None

    def update(self, instance, validated_data):
        # G2: stock is derived from the ledger. `Product.stock_qty` is only an opening figure
        # taken when a product is created; after that it is read-only, so it can no longer be
        # edited into disagreement with the ledger. Stock is added by receiving a batch.
        validated_data.pop("stock_qty", None)
        return super().update(instance, validated_data)




# Define a serializer for the ProductFaq model
class ProductFaqSerializer(SafeDepthModelSerializer):
    # Serialize the related Product model
    product = ProductSerializer()

    class Meta:
        model = ProductFaq
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(ProductFaqSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new product FAQ, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CartOrderItem model
class CartSerializer(SafeDepthModelSerializer):
    # Serialize the related Product model
    product = ProductSerializer()  

    class Meta:
        model = Cart
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super(CartSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order item, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CartOrderItem model
class CartOrderItemSerializer(SafeDepthModelSerializer):
    # Serialize the related Product model
    # product = ProductSerializer()  

    class Meta:
        model = CartOrderItem
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super(CartOrderItemSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order item, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CartOrder model
class CartOrderSerializer(SafeDepthModelSerializer):
    # Serialize related CartOrderItem models
    orderitem = CartOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = CartOrder
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CartOrderSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3


class VendorSerializer(SafeDepthModelSerializer):
    # Public view of the shop owner: never email, phone or credentials
    user = PublicUserSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(VendorSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cart order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Review model
class ReviewSerializer(SafeDepthModelSerializer):
    # Serialize the related Product model
    product = ProductSerializer()
    profile = PublicProfileSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(ReviewSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new review, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Wishlist model
class WishlistSerializer(SafeDepthModelSerializer):
    # Serialize the related Product model
    product = ProductSerializer()

    class Meta:
        model = Wishlist
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(WishlistSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new wishlist item, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Address model
class AddressSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Address
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(AddressSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new address, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CancelledOrder model
class CancelledOrderSerializer(SafeDepthModelSerializer):

    class Meta:
        model = CancelledOrder
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CancelledOrderSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new cancelled order, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the Coupon model
class CouponSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Coupon
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CouponSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the CouponUsers model
class CouponUsersSerializer(SafeDepthModelSerializer):
    # Serialize the related Coupon model
    coupon =  CouponSerializer()

    class Meta:
        model = CouponUsers
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(CouponUsersSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon user, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3

# Define a serializer for the DeliveryCouriers model
class DeliveryCouriersSerializer(SafeDepthModelSerializer):

    class Meta:
        model = DeliveryCouriers
        fields = '__all__'


class NotificationSerializer(SafeDepthModelSerializer):

    class Meta:
        model = Notification
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(NotificationSerializer, self).__init__(*args, **kwargs)
        # Customize serialization depth based on the request method.
        request = self.context.get('request')
        if request and request.method == 'POST':
            # When creating a new coupon user, set serialization depth to 0.
            self.Meta.depth = 0
        else:
            # For other methods, set serialization depth to 3.
            self.Meta.depth = 3


class SummarySerializer(serializers.Serializer):
    products = serializers.IntegerField()
    orders = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)

class EarningSummarySerializer(serializers.Serializer):
    monthly_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)


class CouponSummarySerializer(serializers.Serializer):
    total_coupons = serializers.IntegerField(default=0)
    active_coupons = serializers.IntegerField(default=0)


class NotificationSummarySerializer(serializers.Serializer):
    un_read_noti = serializers.IntegerField(default=0)
    read_noti = serializers.IntegerField(default=0)
    all_noti = serializers.IntegerField(default=0)