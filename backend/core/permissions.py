from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaffOwner(BasePermission):
    """
    Single-brand owner/staff access. The brand owner and their team are Django staff users
    (is_staff=True). Customers never pass this check.
    """

    message = "Staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


class PublicReadStaffWrite(BasePermission):
    """Anyone may read; only staff may write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


def ensure_self_or_staff(request, user_id):
    """
    Raise 403 unless the authenticated user is the user identified by `user_id`
    (as passed in a URL or body) or is staff. Returns the int user id.
    """
    user = request.user
    if not (user and user.is_authenticated):
        raise PermissionDenied("Authentication required.")
    try:
        requested = int(user_id)
    except (TypeError, ValueError):
        raise PermissionDenied("Invalid user.")
    if requested != user.pk and not user.is_staff:
        raise PermissionDenied("You do not have access to this resource.")
    return requested


def ensure_order_access(request, order):
    """
    Orders are addressable by their random `oid` so guests can complete checkout.
    Once an order belongs to a registered buyer, only that buyer (or staff) may read or act on it.
    """
    if order.buyer_id is None:
        return
    user = request.user
    if user and user.is_authenticated and (user.pk == order.buyer_id or user.is_staff):
        return
    raise PermissionDenied("You do not have access to this order.")
