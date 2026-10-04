"""
Idempotency helpers backed by core.ProcessedEvent.

Usage:
    with transaction.atomic():
        if not claim_event("paypal", paypal_order_id):
            return  # duplicate, already handled
        ... apply the side effect ...

Because the claim and the side effect share one transaction, a failure in the side
effect rolls the claim back and a retry can succeed.
"""

from django.db import IntegrityError, transaction

from core.models import ProcessedEvent


def claim_event(provider, event_id, note=""):
    """Return True if this (provider, event_id) was claimed now, False if it was already processed."""
    if not provider or not event_id:
        raise ValueError("provider and event_id are required")
    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(provider=str(provider)[:50], event_id=str(event_id)[:255], note=note[:255])
        return True
    except IntegrityError:
        return False


def is_processed(provider, event_id):
    return ProcessedEvent.objects.filter(provider=provider, event_id=str(event_id)).exists()
