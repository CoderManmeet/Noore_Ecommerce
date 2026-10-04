"""Periodic store jobs, run by `python manage.py run_worker`."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.audit import acting_as
from core.jobs import periodic
from store.order_state import OrderStateError, set_payment_status

logger = logging.getLogger(__name__)

DRAFT_PAYMENT_STATUSES = ("initiated", "processing")


def expire_stale_order_drafts(now=None):
    """
    Expire unpaid order drafts older than ORDER_DRAFT_TTL_HOURS.

    Goes through the order state machine, so the draft's stock holds are released and the
    change is audited. An expired order no longer counts against a coupon's caps
    (store.pricing.live_redemptions) and its cart can start a fresh order.
    Idempotent: an order that is already expired is not selected again. Returns the count.
    """
    from store.models import CartOrder

    now = now or timezone.now()
    cutoff = now - timedelta(hours=settings.ORDER_DRAFT_TTL_HOURS)
    expired = 0
    stale = CartOrder.objects.filter(payment_status__in=DRAFT_PAYMENT_STATUSES, date__lt=cutoff).exclude(
        order_status="Cancelled"
    )
    for order in stale.iterator():
        try:
            with acting_as(None, label="system:worker"):
                set_payment_status(order, "expired", reason="unpaid order draft timed out")
            expired += 1
        except OrderStateError:
            logger.exception("could not expire order draft %s", order.pk)
    return expired


@periodic("store.expire_stale_order_drafts", every_seconds=3600)
def expire_stale_order_drafts_job(payload):
    count = expire_stale_order_drafts()
    if count:
        logger.info("expired %s stale order draft(s)", count)


def reconcile_pending_payments(now=None):
    """
    Ask Razorpay about prepaid orders that have been started but not confirmed for a few
    minutes, so a missed webhook cannot strand an order the customer has paid for.
    Idempotent: confirmation goes through the same claim-once path as the webhook.
    Returns the number of orders confirmed.
    """
    from store.models import CartOrder
    from store.payments import RAZORPAY, PaymentError, is_enabled
    from store.payments.razorpay import is_configured, reconcile_order

    if not is_enabled(RAZORPAY) or not is_configured():
        return 0
    now = now or timezone.now()
    older_than = now - timedelta(minutes=settings.PAYMENT_RECONCILE_AFTER_MINUTES)
    newer_than = now - timedelta(hours=settings.ORDER_DRAFT_TTL_HOURS + 24)
    candidates = CartOrder.objects.filter(
        payment_provider=RAZORPAY, payment_status__in=DRAFT_PAYMENT_STATUSES + ("expired",),
        date__lt=older_than, date__gt=newer_than,
    ).exclude(razorpay_order_id="")
    confirmed = 0
    for order in candidates.iterator():
        try:
            if reconcile_order(order) in ("paid", "flagged"):
                confirmed += 1
        except PaymentError:
            logger.warning("could not reconcile order %s with razorpay; will retry", order.pk)
    return confirmed


@periodic("store.reconcile_pending_payments", every_seconds=120)
def reconcile_pending_payments_job(payload):
    count = reconcile_pending_payments()
    if count:
        logger.info("reconciled %s payment(s) with razorpay", count)


def queue_review_requests(now=None):
    """
    One review-request email per delivered order, REVIEW_REQUEST_DELAY_DAYS after delivery.
    No reminders: the email job's dedupe key makes it once per order for good.
    """
    from store.emails import KIND_REVIEW_REQUEST, queue_order_email
    from store.models import CartOrder

    now = now or timezone.now()
    due_before = now - timedelta(days=settings.REVIEW_REQUEST_DELAY_DAYS)
    not_older_than = due_before - timedelta(days=14)
    queued = 0
    due = CartOrder.objects.filter(delivered_at__lte=due_before, delivered_at__gte=not_older_than).exclude(
        order_status="Cancelled").exclude(email="")
    for order in due.iterator():
        queue_order_email(order, KIND_REVIEW_REQUEST)
        queued += 1
    return queued


@periodic("store.queue_review_requests", every_seconds=3600)
def queue_review_requests_job(payload):
    queue_review_requests()
