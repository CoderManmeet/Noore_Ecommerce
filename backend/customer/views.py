# Django Packages
from django.shortcuts import get_object_or_404

# Restframework Packages
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Serializers
from store.serializers import CartOrderSerializer, NotificationSerializer, WishlistSerializer
from userauths.serializer import ProfileSerializer

# Models
from store.models import CartOrder, Notification, Product, Wishlist
from userauths.models import Profile

from core.permissions import ensure_self_or_staff

# An order a customer has actually placed: paid, Cash on Delivery awaiting payment ("pending"),
# or since refunded/cancelled. Unpaid checkout drafts and expired ones are not shown.
PLACED_PAYMENT_STATUSES = ("paid", "pending", "refunding", "refunded", "cancelled")


class OrdersAPIView(generics.ListAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['user_id'])
        return CartOrder.objects.filter(buyer_id=user_id, payment_status__in=PLACED_PAYMENT_STATUSES)


class OrdersDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = 'user_id'

    def get_object(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['user_id'])
        return get_object_or_404(CartOrder, buyer_id=user_id, payment_status__in=PLACED_PAYMENT_STATUSES,
                                 oid=self.kwargs['order_oid'])


class WishlistCreateAPIView(generics.CreateAPIView):
    serializer_class = WishlistSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request):
        payload = request.data
        product = get_object_or_404(Product, id=payload.get('product_id'))
        if payload.get('user_id') not in (None, "", "undefined"):
            ensure_self_or_staff(request, payload.get('user_id'))
        user = request.user

        wishlist = Wishlist.objects.filter(product=product, user=user)
        if wishlist.exists():
            wishlist.delete()
            return Response({"message": "Removed From Wishlist"}, status=status.HTTP_200_OK)
        Wishlist.objects.create(product=product, user=user)
        return Response({"message": "Added To Wishlist"}, status=status.HTTP_201_CREATED)


class WishlistAPIView(generics.ListAPIView):
    serializer_class = WishlistSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['user_id'])
        return Wishlist.objects.filter(user_id=user_id)


class CustomerNotificationView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['user_id'])
        return Notification.objects.filter(user_id=user_id)


class CustomerUpdateView(generics.RetrieveUpdateAPIView):
    """
    The URL segment is the user's id (that is what the frontend sends). The profile is looked
    up by user, never by profile primary key.
    """

    serializer_class = ProfileSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['pk'])
        profile, _created = Profile.objects.get_or_create(user_id=user_id)
        return profile
