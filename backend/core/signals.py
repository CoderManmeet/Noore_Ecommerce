"""
Audit signal handlers.

For each registered model we snapshot the tracked fields before save and, after save,
write one AuditLog row when any of them changed (or when the row was created).
Signals cover every write path: API views, Django admin, shell and management commands.
"""

from django.db.models.signals import post_delete, post_save, pre_save

from core.audit import record, snapshot
from store.models import CartOrder, CartOrderItem, Product

TRACKED_FIELDS = {
    Product: ["price", "old_price", "shipping_amount", "stock_qty", "status"],
    CartOrder: ["payment_status", "order_status", "total", "total_paise"],
    CartOrderItem: ["delivery_status", "tracking_id", "delivery_couriers", "qty", "total"],
}

ACTION_PREFIX = {
    Product: "product",
    CartOrder: "order",
    CartOrderItem: "order_item",
}


def _capture_before(sender, instance, **kwargs):
    fields = TRACKED_FIELDS[sender]
    if instance.pk is None:
        instance._audit_before = None
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._audit_before = snapshot(previous, fields) if previous is not None else None


def _write_after(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    fields = TRACKED_FIELDS[sender]
    prefix = ACTION_PREFIX[sender]
    after = snapshot(instance, fields)
    before = getattr(instance, "_audit_before", None)
    if created or before is None:
        record(f"{prefix}.created", instance, before=None, after=after)
    else:
        changed_before = {k: v for k, v in before.items() if after.get(k) != v}
        if changed_before:
            changed_after = {k: after[k] for k in changed_before}
            record(f"{prefix}.updated", instance, before=changed_before, after=changed_after)
    instance._audit_before = None


def _write_delete(sender, instance, **kwargs):
    record(f"{ACTION_PREFIX[sender]}.deleted", instance, before=snapshot(instance, TRACKED_FIELDS[sender]), after=None)


for _model in TRACKED_FIELDS:
    pre_save.connect(_capture_before, sender=_model, dispatch_uid=f"core_audit_pre_{_model.__name__}")
    post_save.connect(_write_after, sender=_model, dispatch_uid=f"core_audit_post_{_model.__name__}")
    post_delete.connect(_write_delete, sender=_model, dispatch_uid=f"core_audit_del_{_model.__name__}")
