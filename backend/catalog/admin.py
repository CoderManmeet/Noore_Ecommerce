from django.contrib import admin

from catalog.models import PriceHistory, ProductVariant
from inventory.services import available_qty, on_hand_qty


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "name", "options", "price_rupees", "mrp_rupees", "perishable", "is_default",
                    "active", "on_hand", "available"]
    list_filter = ["active", "is_default", "perishable"]
    search_fields = ["sku", "name", "product__title"]
    autocomplete_fields = ["product"]

    @admin.display(description="Price")
    def price_rupees(self, obj):
        from core.money import format_inr

        return format_inr(obj.price_paise)

    @admin.display(description="MRP")
    def mrp_rupees(self, obj):
        from core.money import format_inr

        return format_inr(obj.mrp_paise) if obj.mrp_paise else "-"

    @admin.display(description="On hand")
    def on_hand(self, obj):
        return on_hand_qty(obj)

    @admin.display(description="Available")
    def available(self, obj):
        return available_qty(obj)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    """Read-only: rows are written by a signal on every price change and are append-only."""

    list_display = ["effective_from", "variant", "price_rupees", "mrp_rupees", "actor_label"]
    list_filter = ["effective_from"]
    search_fields = ["variant__sku", "variant__product__title"]
    date_hierarchy = "effective_from"
    readonly_fields = [f.name for f in PriceHistory._meta.fields]

    @admin.display(description="Price")
    def price_rupees(self, obj):
        from core.money import format_inr

        return format_inr(obj.price_paise)

    @admin.display(description="MRP")
    def mrp_rupees(self, obj):
        from core.money import format_inr

        return format_inr(obj.mrp_paise) if obj.mrp_paise else "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
