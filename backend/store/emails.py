"""
Order emails, sent in the background through core.jobs (Phase G3).

    queue_order_email(order, "placed")

Each (kind, order) is sent at most once: the job is enqueued with a dedupe key, so calling
queue_order_email twice (a duplicate webhook, a retried request) still sends one email.
Bodies are built here from the order's stored paise values; no address, phone number or
message body is ever logged.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.jobs import enqueue, job
from core.money import format_inr

logger = logging.getLogger(__name__)

JOB_NAME = "store.send_order_email"

KIND_PLACED = "placed"
KIND_PAID = "paid"
KIND_SHIPPED = "shipped"
KIND_CANCELLED = "cancelled"
KIND_REVIEW_REQUEST = "review_request"
KIND_ACCOUNT_INVITE = "account_invite"
KINDS = (KIND_PLACED, KIND_PAID, KIND_SHIPPED, KIND_CANCELLED, KIND_REVIEW_REQUEST)


def queue_order_email(order, kind):
    """Enqueue one email of this kind for this order. Idempotent."""
    if kind not in KINDS:
        raise ValueError(f"unknown order email kind {kind!r}")
    return enqueue(JOB_NAME, {"order_id": order.pk, "kind": kind}, dedupe_key=f"order-email:{kind}:{order.pk}")


def _tracking_lines(items):
    lines = []
    for item in items:
        if not item.tracking_id:
            continue
        courier = item.delivery_couriers
        text = f"Tracking number: {item.tracking_id}"
        if courier is not None and courier.name:
            text += f" ({courier.name})"
        if courier is not None and courier.tracking_website:
            parameter = courier.url_parameter or ""
            link = f"{courier.tracking_website}?{parameter}={item.tracking_id}" if parameter else courier.tracking_website
            text += f" - {link}"
        if text not in lines:
            lines.append(text)
    return lines


def build_order_email(order, kind):
    """Return (subject, context) for one order email."""
    items = list(order.orderitem.select_related("product", "variant", "delivery_couriers").order_by("id"))
    is_cod = (order.payment_method or "").upper() == "COD"
    total = format_inr(int(order.total_paise))
    store = settings.STORE_NAME
    extra = []
    action_url = action_label = ""

    if kind == KIND_PLACED:
        subject = f"We have your order {order.oid}"
        if is_cod:
            intro = (f"Thank you for your order. It is Cash on Delivery: please keep {total} ready to pay "
                     "when it arrives. We may call or message you to confirm the order before we send it.")
        else:
            intro = ("Thank you for your order. We are waiting for your payment to be confirmed and will "
                     "email you as soon as it is.")
    elif kind == KIND_PAID:
        subject = f"Payment received for order {order.oid}"
        intro = f"We have received your payment of {total}. We will email you again when your order is on its way."
    elif kind == KIND_SHIPPED:
        subject = f"Your order {order.oid} is on its way"
        intro = "Your order has been shipped."
        extra = _tracking_lines(items)
        if is_cod:
            extra.append(f"Please keep {total} ready to pay on delivery.")
    elif kind == KIND_CANCELLED:
        subject = f"Your order {order.oid} has been cancelled"
        intro = "Your order has been cancelled."
        if order.payment_status in ("refunding", "refunded"):
            extra.append("Your payment is being refunded to the original payment method.")
    else:  # KIND_REVIEW_REQUEST
        subject = f"How was your order from {store}?"
        intro = ("We hope you are enjoying your order. If you have a minute, we would love an honest review. "
                 "Sign in to your account, open the product and write your review.")
        action_url = f"{settings.SITE_URL}/customer/orders/"
        action_label = "Go to my orders"

    context = {
        "store_name": store,
        "order": order,
        "intro": intro,
        "extra_lines": extra,
        "items": [
            {
                "title": item.product.title,
                "variant": item.variant.name if item.variant_id and item.variant.name != "Default" else "",
                "qty": item.qty,
                "amount": format_inr(int(item.sub_total_paise)),
            }
            for item in items
        ],
        "subtotal": format_inr(int(order.sub_total_paise)),
        "discount": format_inr(int(order.saved_paise)) if order.saved_paise else "",
        "coupon_code": order.coupon_code,
        "shipping": format_inr(int(order.shipping_amount_paise)) if order.shipping_amount_paise else "Free",
        "total": total,
        "is_cod": is_cod,
        "show_totals": kind != KIND_REVIEW_REQUEST,
        "action_url": action_url,
        "action_label": action_label,
    }
    return subject, context


def _send(to, subject, context):
    text_body = render_to_string("email/order_update.txt", context)
    html_body = render_to_string("email/order_update.html", context)
    message = EmailMultiAlternatives(subject=subject, from_email=settings.FROM_EMAIL, to=[to], body=text_body)
    message.attach_alternative(html_body, "text/html")
    message.send()


@job(JOB_NAME)
def send_order_email_job(payload):
    """
    Deliver one order email. At-least-once delivery from the job runner is made effectively
    once by the dedupe key on enqueue; a retry after a mail-server error re-sends, which is the
    intended behaviour (the previous attempt did not go out).
    """
    from store.models import CartOrder

    order = CartOrder.objects.filter(pk=payload.get("order_id")).first()
    kind = payload.get("kind")
    if order is None or kind not in KINDS or not order.email:
        return
    subject, context = build_order_email(order, kind)
    _send(order.email, subject, context)
    logger.info("order email %s sent for order %s", kind, order.pk)


ACCOUNT_INVITE_JOB = "store.send_account_invite"


@job(ACCOUNT_INVITE_JOB)
def send_account_invite_job(payload):
    """Email the set-password link to the address on a guest order."""
    from store.account_claim import build_claim_link
    from store.models import CartOrder

    order = CartOrder.objects.filter(pk=payload.get("order_id")).first()
    if order is None or not order.email:
        return
    context = {
        "store_name": settings.STORE_NAME,
        "order": order,
        "intro": (f"Create your {settings.STORE_NAME} account to track order {order.oid} and reorder in one tap. "
                  f"Choose a password using the link below. It works for {settings.ACCOUNT_CLAIM_LINK_HOURS} hours. "
                  "If you did not ask for this, you can ignore this email."),
        "extra_lines": [],
        "items": [],
        "show_totals": False,
        "action_url": build_claim_link(order),
        "action_label": "Create my account",
    }
    _send(order.email, f"Create your {settings.STORE_NAME} account", context)
    logger.info("account invite sent for order %s", order.pk)
