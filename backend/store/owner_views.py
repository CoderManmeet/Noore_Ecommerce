"""
Owner (staff) endpoints for running orders and moderating reviews (Phases G3 and G4).

Every status change goes through store/order_state.py, so it is validated and audited with
the signed-in staff user as the actor. Staff only: core.permissions.IsStaffOwner.
"""

import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import record
from core.permissions import IsStaffOwner
from store.emails import queue_order_email
from store.models import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    CartOrder,
    DeliveryCouriers,
    Review,
)
from store.order_state import (
    CODNotConfirmed,
    OrderStateError,
    advance_order_delivery,
    cancel_order,
    confirm_cod,
    mark_paid,
    set_payment_status,
)
from store.serializers import CartOrderSerializer, ReviewSerializer

logger = logging.getLogger(__name__)

# Orders the owner works with: everything a customer actually placed. Unpaid checkout drafts
# are left out unless asked for with ?drafts=1.
PLACED = ("paid", "pending", "refunding", "refunded", "cancelled")


class OwnerOrderListView(generics.ListAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        queryset = CartOrder.objects.all().order_by("-date")
        if self.request.GET.get("drafts") != "1":
            queryset = queryset.filter(payment_status__in=PLACED)
        return queryset


class OwnerOrderDetailView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsStaffOwner,)

    def get_object(self):
        return get_object_or_404(CartOrder, oid=self.kwargs["order_oid"])


class OwnerOrderActionView(APIView):
    """
    POST {"action": ...} on one order:

      confirm_cod            the customer confirmed the COD order (needed before dispatch)
      set_delivery           {"status": "Shipping Processing"|"Shipped"|"Arrived"|"Delivered",
                              "tracking_id": "...", "courier_id": 1}
      mark_paid              cash collected on a delivered COD order
      cancel                 cancel the order and give its stock back
      record_refund          the refund was issued in the Razorpay dashboard: paid -> refunded
      clear_attention        the flagged problem has been dealt with
    """

    permission_classes = (IsStaffOwner,)

    def post(self, request, order_oid, *args, **kwargs):
        order = get_object_or_404(CartOrder, oid=order_oid)
        action = str(request.data.get("action") or "")
        reason = str(request.data.get("reason") or "")[:200]
        actor = request.user
        try:
            if action == "confirm_cod":
                order = confirm_cod(order, actor=actor, reason=reason or "confirmed with the customer")
            elif action == "set_delivery":
                order = self._set_delivery(request, order, actor, reason)
            elif action == "mark_paid":
                if (order.payment_method or "").upper() != "COD":
                    return self._error("Only a Cash on Delivery order is marked paid by hand. Online payments are confirmed by Razorpay.")
                order = mark_paid(order, reason=reason or "cash collected on delivery", actor=actor)
                queue_order_email(order, "paid")
            elif action == "cancel":
                order = cancel_order(order, reason=reason or "cancelled by the owner", actor=actor)
                queue_order_email(order, "cancelled")
            elif action == "record_refund":
                order = set_payment_status(order, "refunded", reason=reason or "refund issued in the Razorpay dashboard", actor=actor)
            elif action == "clear_attention":
                before = order.needs_attention
                CartOrder.objects.filter(pk=order.pk).update(needs_attention="")
                record("order.needs_attention", order, before={"needs_attention": before},
                       after={"needs_attention": ""}, reason=reason or "resolved by the owner", actor=actor)
            else:
                return self._error("Unknown action.")
        except CODNotConfirmed as exc:
            return self._error(str(exc), status.HTTP_409_CONFLICT)
        except OrderStateError as exc:
            return self._error(str(exc))

        order = CartOrder.objects.get(pk=order.pk)
        return Response(CartOrderSerializer(order, context={"request": request}).data)

    def _set_delivery(self, request, order, actor, reason):
        target = str(request.data.get("status") or "")
        tracking_id = request.data.get("tracking_id")
        tracking_id = str(tracking_id).strip()[:200] if tracking_id not in (None, "") else None
        courier = None
        courier_id = request.data.get("courier_id")
        if courier_id not in (None, "", "null"):
            courier = DeliveryCouriers.objects.filter(pk=courier_id).first()
            if courier is None:
                raise OrderStateError("That courier does not exist.")
        was_shipped = order.orderitem.filter(delivery_status__in=["Shipped", "Arrived", "Delivered"]).exists()
        order = advance_order_delivery(order, target, actor=actor, reason=reason,
                                       tracking_id=tracking_id, courier=courier)
        if not was_shipped and target in ("Shipped", "Arrived", "Delivered"):
            queue_order_email(order, "shipped")
        return order

    @staticmethod
    def _error(message, code=status.HTTP_400_BAD_REQUEST):
        return Response({"message": message}, status=code)


class OwnerReviewListView(generics.ListAPIView):
    """The moderation queue. ?status=PENDING (default), APPROVED, REJECTED or ALL."""

    serializer_class = ReviewSerializer
    permission_classes = (IsStaffOwner,)

    def get_queryset(self):
        wanted = str(self.request.GET.get("status") or REVIEW_PENDING).upper()
        queryset = Review.objects.all().order_by("-date")
        if wanted != "ALL":
            queryset = queryset.filter(status=wanted)
        return queryset


class OwnerReviewModerateView(APIView):
    """
    POST {"action": "approve" | "reject"}. Audited with the staff user.
    Rejecting is for abuse and spam, not for low ratings.
    """

    permission_classes = (IsStaffOwner,)

    def post(self, request, review_id, *args, **kwargs):
        review = get_object_or_404(Review, pk=review_id)
        action = str(request.data.get("action") or "")
        target = {"approve": REVIEW_APPROVED, "reject": REVIEW_REJECTED}.get(action)
        if target is None:
            return Response({"message": "Action must be approve or reject."}, status=status.HTTP_400_BAD_REQUEST)

        before = review.status
        if before != target:
            review.status = target
            review.moderated_by = request.user
            review.moderated_at = timezone.now()
            review.save()  # also re-computes the product's rating (existing signal)
            record("review.moderated", review, before={"status": before}, after={"status": target},
                   reason=str(request.data.get("reason") or "")[:200], actor=request.user)
        return Response({"id": review.pk, "status": review.status})
