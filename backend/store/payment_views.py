"""
Checkout payment endpoints (Phase G3): Razorpay and Cash on Delivery, plus the guest
"create an account" link.

An order is addressed by its random `oid` so guests can pay; an order that belongs to a
registered buyer is only usable by that buyer or staff (core.permissions.ensure_order_access).
The amount is always the order's stored `total_paise`; nothing about money is read from the request.
"""

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.jobs import enqueue
from core.permissions import ensure_order_access
from store import payments
from store.account_claim import ClaimError, claim_account
from store.emails import ACCOUNT_INVITE_JOB, queue_order_email
from store.models import CartOrder
from store.order_state import OrderStateError, StockUnavailable, place_cod_order
from store.payments import PaymentError

logger = logging.getLogger(__name__)


def _order_for(request, order_oid):
    order = CartOrder.objects.filter(oid=order_oid).first()
    if order is None:
        return None
    ensure_order_access(request, order)
    return order


def _clear_cart(order):
    from store.views import _clear_cart_for_order

    _clear_cart_for_order(order)


class PaymentMethodsView(APIView):
    """Which payment methods checkout should offer. Contains nothing secret."""

    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        from store.payments.razorpay import is_configured

        return Response({
            "razorpay": payments.is_enabled(payments.RAZORPAY),
            "razorpay_configured": is_configured(),
            "cod": payments.is_enabled(payments.COD),
        })


class RazorpayStartView(APIView):
    """Create the Razorpay order for this order's stored total and return the checkout options."""

    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def post(self, request, order_oid, *args, **kwargs):
        order = _order_for(request, order_oid)
        if order is None:
            return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            options = payments.get_provider(payments.RAZORPAY).create_payment(order)
        except PaymentError as exc:
            return Response({"message": exc.message}, status=exc.status)
        return Response({"options": options, "order_oid": order.oid})


class RazorpayReturnView(APIView):
    """
    The browser is back from Razorpay Checkout. Verifies the signature and answers
    "confirming": the order is NOT marked paid here. The page then polls the order until the
    webhook (or the reconcile job) confirms the payment.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def post(self, request, *args, **kwargs):
        order = _order_for(request, request.data.get("order_oid"))
        if order is None:
            return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            payments.get_provider(payments.RAZORPAY).verify_return(order, request.data)
        except PaymentError as exc:
            return Response({"message": exc.message}, status=exc.status)
        if order.payment_status != "paid":
            queue_order_email(order, "placed")
        return Response({"message": "confirming", "order_oid": order.oid, "payment_status": order.payment_status})


class RazorpayWebhookView(APIView):
    """
    Razorpay's server-to-server notification. Unauthenticated by design: the signature over
    the RAW body is the authentication. This is the only request that marks an order paid.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "webhook"

    def post(self, request, *args, **kwargs):
        if not payments.is_enabled(payments.RAZORPAY):
            return Response({"message": "not enabled"}, status=status.HTTP_403_FORBIDDEN)
        raw_body = request._request.body  # the exact bytes Razorpay signed; never the parsed data
        from store.payments.razorpay import RazorpayProvider

        code, result = RazorpayProvider().handle_webhook(raw_body, request.headers)
        return Response({"result": result}, status=code)


class PlaceCodOrderView(APIView):
    """Place the order as Cash on Delivery. Nothing is charged; the stock is kept for the order."""

    permission_classes = (AllowAny,)
    throttle_scope = "checkout"

    def post(self, request, order_oid, *args, **kwargs):
        if not payments.is_enabled(payments.COD):
            return Response({"message": "Cash on Delivery is not available."}, status=status.HTTP_403_FORBIDDEN)
        order = _order_for(request, order_oid)
        if order is None:
            return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            with transaction.atomic():
                order = place_cod_order(order)
        except StockUnavailable as exc:
            return Response({"message": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderStateError as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _clear_cart(order)
        if order.buyer_id:
            from store.views import send_notification

            send_notification(user=order.buyer, order=order)
        queue_order_email(order, "placed")
        return Response({"message": "Order placed", "order_oid": order.oid, "payment_status": order.payment_status})


class AccountInviteView(APIView):
    """
    A guest asks for a "create your account" link for their order. The link only ever goes to
    the email address on the order. The answer is the same whether or not anything was sent.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request, *args, **kwargs):
        order = CartOrder.objects.filter(oid=request.data.get("order_oid")).first()
        if order is not None and order.buyer_id is None and order.email \
                and order.payment_status in ("paid", "pending"):
            enqueue(ACCOUNT_INVITE_JOB, {"order_id": order.pk}, dedupe_key=f"account-invite:{order.pk}")
        return Response({"message": "If this order can be linked to an account, we have emailed a link to the address on the order."})


class AccountClaimView(APIView):
    """Use the emailed link: set a password, create the account, attach that email's guest orders."""

    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request, *args, **kwargs):
        try:
            user, created, attached = claim_account(request.data.get("token"), str(request.data.get("password") or ""))
        except ClaimError as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if created:
            message = "Your account is ready. Sign in with your email and the password you just chose."
        else:
            message = "You already have an account with this email. Your order has been added to it; please sign in."
        return Response({"message": message, "created": created, "orders_attached": attached, "email": user.email})
