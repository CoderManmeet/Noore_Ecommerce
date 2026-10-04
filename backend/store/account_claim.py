"""
"Create an account to track this order" for guests (Phase G3).

A guest who placed an order can ask for a set-password link. The link is emailed to the
address on the order, so using it proves the person controls that mailbox. Only then is an
account created for that email and every guest order placed with that email attached to it.
Orders are never attached to an email that has not been verified this way.

The link carries a signed, time-limited token (django.core.signing); nothing is stored.
"""

import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from core.audit import record

logger = logging.getLogger(__name__)

SALT = "store.account-claim.v1"


class ClaimError(Exception):
    """The link is invalid or expired, or the password is not acceptable."""


def normalise_email(value):
    return str(value or "").strip().lower()


def make_token(order):
    return signing.dumps({"email": normalise_email(order.email), "oid": order.oid}, salt=SALT)


def read_token(token):
    try:
        data = signing.loads(str(token or ""), salt=SALT, max_age=settings.ACCOUNT_CLAIM_LINK_HOURS * 3600)
    except signing.SignatureExpired:
        raise ClaimError("This link has expired. Ask for a new one from your order page.")
    except signing.BadSignature:
        raise ClaimError("This link is not valid.")
    if not isinstance(data, dict) or not data.get("email"):
        raise ClaimError("This link is not valid.")
    return data


def build_claim_link(order):
    return f"{settings.SITE_URL}/claim-account?token={make_token(order)}"


def attach_guest_orders(user, email):
    """Give this user every guest order placed with this (verified) email. Returns the count."""
    from store.models import CartOrder

    attached = 0
    for order in CartOrder.objects.filter(buyer__isnull=True, email__iexact=email):
        CartOrder.objects.filter(pk=order.pk, buyer__isnull=True).update(buyer=user)
        record("order.attached_to_account", order, before={"buyer": None}, after={"buyer": user.pk},
               reason="email verified through the account link", actor=user)
        attached += 1
    return attached


@transaction.atomic
def claim_account(token, password):
    """
    Use a link: create the account for the link's email (or find the one that already exists)
    and attach that email's guest orders. Returns (user, created, attached_count).

    If an account already exists for the email its password is NOT changed here (that is what
    "forgot password" is for); the verified guest orders are still attached to it.
    """
    from store.models import CartOrder
    from userauths.models import User

    data = read_token(token)
    email = data["email"]

    user = User.objects.filter(email__iexact=email).first()
    created = False
    if user is None:
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise ClaimError(" ".join(exc.messages))
        order = CartOrder.objects.filter(oid=data.get("oid")).first()
        user = User(
            email=email,
            username=email.split("@")[0][:150],
            full_name=(order.full_name if order is not None else "")[:500],
            phone=(order.mobile if order is not None else "")[:500],
        )
        user.set_password(password)
        user.save()
        created = True
        logger.info("account created from an order link for user %s", user.pk)

    attached = attach_guest_orders(user, email)
    return user, created, attached
