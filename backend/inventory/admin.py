from django.contrib import admin

from catalog.models import ProductVariant
from inventory.models import Batch, StockMovement, StockReservation
from inventory.services import batch_on_hand, receive_production


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ["batch_code", "variant", "manufactured_on", "best_before", "quantity_produced", "remaining", "is_expired"]
    list_filter = ["best_before", "manufactured_on"]
    search_fields = ["batch_code", "variant__sku"]
    autocomplete_fields = ["variant"]

    def get_readonly_fields(self, request, obj=None):
        # Once a batch exists its variant and produced quantity are part of the ledger.
        return ["variant", "quantity_produced"] if obj is not None else []

    def save_model(self, request, obj, form, change):
        """
        Adding a batch here is how the owner receives stock: the produced quantity is booked
        into the ledger through inventory.services, attributed to the signed-in staff user.
        Editing an existing batch never touches the ledger.
        """
        super().save_model(request, obj, form, change)
        if not change:
            receive_production(obj.variant, obj, obj.quantity_produced, reason="Batch added in admin",
                               actor=request.user)

    @admin.display(description="Remaining")
    def remaining(self, obj):
        return batch_on_hand(obj)

    @admin.display(boolean=True, description="Expired")
    def is_expired(self, obj):
        return obj.is_expired


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Read-only: stock is changed through inventory.services, never by hand."""

    list_display = ["created_at", "variant", "batch", "kind", "quantity", "channel", "actor_label", "reason"]
    list_filter = ["kind", "channel", "created_at"]
    search_fields = ["variant__sku", "batch__batch_code", "reference_id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "variant", "batch", "quantity", "status", "expires_at", "order", "resolved_at"]
    list_filter = ["status"]
    search_fields = ["variant__sku", "cart_id", "order__oid"]
    readonly_fields = [f.name for f in StockReservation._meta.fields]

    def has_add_permission(self, request):
        return False
