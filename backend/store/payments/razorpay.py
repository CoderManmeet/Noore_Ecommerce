"""
Razorpay Standard Checkout (Phase G3).

Every request, response field, header and signature rule used here is taken from Razorpay's
published documentation, read on 3 Oct 2026 (nothing is written from memory):

  * https://razorpay.com/docs/developer-tools/integrations/standard-checkout
      - Create Order:  POST {base}/v1/orders, HTTP Basic auth (key id : key secret), JSON body
        {amount (integer paise), currency, receipt (<= 40 chars), notes, capture}.
        Response: {id, entity, amount, amount_paid, amount_due, currency, receipt, status, ...}.
      - Fetch Order:   GET {base}/v1/orders/{order_id} (same order entity).
      - Checkout returns {razorpay_payment_id, razorpay_order_id, razorpay_signature}; the
        signature is HMAC-SHA256(key = key secret, data = order_id + "|" + payment_id), hex,
        using the order id from OUR database.
      - Payment states: `captured` is the one that means the money is confirmed.
      - Webhook event `payment.captured`; payload at payload.payment.entity
        ({id, order_id, amount, ...}).
  * https://razorpay.com/docs/webhooks/validate-test
      - X-Razorpay-Signature = HMAC-SHA256(key = webhook secret, message = RAW request body), hex.
      - x-razorpay-event-id is unique per event and identifies duplicate deliveries.

What means "paid" here: a `payment.captured` webhook with a valid signature whose amount and
currency equal the order's stored total, or (reconcile job) a fetched order whose status is
"paid" with amount_paid equal to the stored total. The browser's return never marks an order paid.
"""

import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings
from django.db import transaction

from core.audit import acting_as, record
from core.idempotency import claim_event
from store.payments import RAZORPAY, PaymentError
from store.payments.base import PaymentProvider

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
CURRENCY = "INR"
PAID_EVENT = "payment.captured"
# Razorpay's documented minimum order amount for INR, in paise.
MINIMUM_AMOUNT_PAISE = 100

DRAFT_PAYMENT_STATUSES = ("initiated", "processing")


def _hmac_hex(key, message):
    if isinstance(key, str):
        key = key.encode()
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _auth():
    return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)


def _api(method, path, payload=None):
    """One call to the Razorpay API. Raises PaymentError; never logs secrets or bodies."""
    url = f"{settings.RAZORPAY_API_BASE}{path}"
    try:
        response = requests.request(method, url, json=payload, auth=_auth(), timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        logger.exception("razorpay %s %s failed to connect", method, path)
        raise PaymentError("The payment service could not be reached. Please try again.", status=502)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        logger.warning("razorpay %s %s returned %s (%s)", method, path, response.status_code, code)
        raise PaymentError("The payment service refused the request. Please try again.", status=502)
    return body


def fetch_order(razorpay_order_id):
    return _api("GET", f"/v1/orders/{razorpay_order_id}")


def verify_checkout_signature(razorpay_order_id, razorpay_payment_id, signature):
    expected = _hmac_hex(settings.RAZORPAY_KEY_SECRET, f"{razorpay_order_id}|{razorpay_payment_id}")
    return hmac.compare_digest(expected, str(signature or ""))


def verify_webhook_signature(raw_body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = _hmac_hex(settings.RAZORPAY_WEBHOOK_SECRET, raw_body)
    return hmac.compare_digest(expected, str(signature))


def flag_for_owner(order, reason):
    """Mark an order as needing the owner's attention (audited). Never raises."""
    from store.models import CartOrder

    before = order.needs_attention
    CartOrder.objects.filter(pk=order.pk).update(needs_attention=reason[:255])
    order.needs_attention = reason[:255]
    record("order.needs_attention", order, before={"needs_attention": before},
           after={"needs_attention": reason[:255]}, reason=reason)


@transaction.atomic
def confirm_paid(razorpay_order_id, amount_paise, currency, payment_id="", source="webhook"):
    """
    Mark the order for this Razorpay order id paid, exactly once.

    Returns one of: "paid", "duplicate", "unknown_order", "mismatch", "flagged".
    The amount and currency must equal the order's stored total; anything else is refused and
    the order is left untouched. The idempotency claim, the status change, the stock securing
    and the flag all commit together or not at all.
    """
    from store.models import CartOrder
    from store.order_state import OrderStateError, mark_paid

    order = CartOrder.objects.select_for_update().filter(razorpay_order_id=razorpay_order_id).first()
    if order is None or not razorpay_order_id:
        logger.warning("razorpay %s for an order id we do not know", source)
        return "unknown_order"

    if str(currency).upper() != CURRENCY or int(amount_paise) != int(order.total_paise):
        logger.warning("razorpay %s amount/currency mismatch for order %s", source, order.pk)
        return "mismatch"

    if not claim_event("razorpay_order_paid", razorpay_order_id, note=f"order:{order.pk} via {source}"):
        return "duplicate"

    with acting_as(None, label=f"system:razorpay-{source}"):
        if payment_id and order.razorpay_payment_id != payment_id:
            order.razorpay_payment_id = payment_id
            order.save(update_fields=["razorpay_payment_id"])

        if order.payment_status == "paid":
            return "duplicate"
        try:
            order = mark_paid(order, reason=f"razorpay {source}: payment captured")
        except OrderStateError:
            # Late payment for an order that is already cancelled or expired: the money has
            # been taken, so the owner must refund it. Never silently marked paid.
            flag_for_owner(order, "Payment received after this order was cancelled or expired. Refund it in the Razorpay dashboard.")
            return "flagged"

    from store.emails import queue_order_email
    from store.views import _clear_cart_for_order, send_notification

    _clear_cart_for_order(order)
    if order.buyer_id:
        send_notification(user=order.buyer, order=order)
    queue_order_email(order, "paid")
    order.refresh_from_db()
    return "flagged" if order.needs_attention else "paid"


class RazorpayProvider(PaymentProvider):
    name = RAZORPAY

    def create_payment(self, order):
        """
        Create (or reuse) the Razorpay order for this order's stored total and return the
        options the browser passes to Razorpay Checkout. A Razorpay order is immutable, so a
        new one is created whenever the stored total has changed since the last one.
        """
        if not is_configured():
            raise PaymentError("Online payment is not configured yet.", status=503)
        if order.payment_status not in DRAFT_PAYMENT_STATUSES or order.order_status == "Cancelled":
            raise PaymentError("This order is not awaiting payment.", status=400)
        amount = int(order.total_paise)
        if amount < MINIMUM_AMOUNT_PAISE:
            raise PaymentError("There is nothing to pay online for this order.", status=400)

        razorpay_order_id = order.razorpay_order_id
        if razorpay_order_id:
            existing = fetch_order(razorpay_order_id)
            if existing.get("status") == "paid":
                raise PaymentError("This order has already been paid. We are confirming it now.", status=409)
            if int(existing.get("amount", -1)) != amount or str(existing.get("currency", "")).upper() != CURRENCY:
                razorpay_order_id = ""

        if not razorpay_order_id:
            created = _api("POST", "/v1/orders", {
                "amount": amount,
                "currency": CURRENCY,
                "receipt": str(order.oid)[:40],
                "notes": {"order_oid": str(order.oid)},
                "capture": "automatic",
            })
            razorpay_order_id = str(created.get("id") or "")
            if not razorpay_order_id or int(created.get("amount", -1)) != amount:
                logger.error("razorpay create order returned an unexpected body for order %s", order.pk)
                raise PaymentError("The payment service returned an unexpected answer. Please try again.", status=502)
            order.razorpay_order_id = razorpay_order_id
            order.payment_provider = RAZORPAY
            order.save(update_fields=["razorpay_order_id", "payment_provider"])
            record("order.payment_started", order, before=None,
                   after={"provider": RAZORPAY, "amount_paise": amount, "currency": CURRENCY})
        elif order.payment_provider != RAZORPAY:
            order.payment_provider = RAZORPAY
            order.save(update_fields=["payment_provider"])

        # Only documented Checkout options are sent. The key id is public by design.
        return {
            "key": settings.RAZORPAY_KEY_ID,
            "amount": amount,
            "currency": CURRENCY,
            "name": settings.STORE_NAME,
            "description": f"Order {order.oid}",
            "order_id": razorpay_order_id,
            "prefill": {
                "name": order.full_name or "",
                "email": order.email or "",
                "contact": order.phone_e164 or order.mobile or "",
            },
            "notes": {"order_oid": str(order.oid)},
        }

    def verify_return(self, order, data):
        """
        The browser came back from Checkout. Check the signature against OUR stored Razorpay
        order id and remember the payment id. This proves the customer went through checkout;
        it does NOT mark the order paid. Only the webhook (or the reconcile job) does that.
        """
        if not is_configured():
            raise PaymentError("Online payment is not configured yet.", status=503)
        payment_id = str(data.get("razorpay_payment_id") or "")
        signature = str(data.get("razorpay_signature") or "")
        if not order.razorpay_order_id or not payment_id or not signature:
            raise PaymentError("Payment details are missing.", status=400)
        if not verify_checkout_signature(order.razorpay_order_id, payment_id, signature):
            logger.warning("razorpay return signature mismatch for order %s", order.pk)
            raise PaymentError("This payment could not be verified.", status=400)
        if order.razorpay_payment_id != payment_id:
            order.razorpay_payment_id = payment_id
            order.save(update_fields=["razorpay_payment_id"])
        return True

    def handle_webhook(self, raw_body, headers):
        """
        Returns (http_status, result). Anything unsigned or forged is 400 and changes nothing.
        A valid event is always answered 200 (so Razorpay stops retrying), including events we
        do not act on and duplicates.
        """
        signature = headers.get("X-Razorpay-Signature") or headers.get("x-razorpay-signature")
        if not verify_webhook_signature(raw_body, signature):
            return 400, "invalid_signature"
        try:
            event = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body)
        except (ValueError, UnicodeDecodeError):
            return 400, "invalid_body"
        if not isinstance(event, dict) or event.get("event") != PAID_EVENT:
            return 200, "ignored"

        try:
            entity = event["payload"]["payment"]["entity"]
            razorpay_order_id = str(entity["order_id"])
            payment_id = str(entity["id"])
            amount = int(entity["amount"])
            currency = str(entity["currency"])
        except (KeyError, TypeError, ValueError):
            # A shape we do not recognise is refused rather than guessed at; the reconcile
            # job will still confirm the order from the Fetch Order API.
            logger.warning("razorpay %s webhook with an unexpected payload shape", PAID_EVENT)
            return 400, "unexpected_payload"

        result = confirm_paid(razorpay_order_id, amount, currency, payment_id=payment_id, source="webhook")
        if result == "mismatch":
            return 400, result
        return 200, result


def reconcile_order(order):
    """
    Ask Razorpay about one prepaid order that is still unconfirmed. If Razorpay says the order
    is paid in full, confirm it through the same path the webhook uses. Returns the result.
    """
    if not order.razorpay_order_id or not is_configured():
        return "skipped"
    remote = fetch_order(order.razorpay_order_id)
    if remote.get("status") != "paid":
        return "not_paid"
    return confirm_paid(order.razorpay_order_id, int(remote.get("amount_paid", -1)), str(remote.get("currency", "")),
                        payment_id="", source="reconcile")
