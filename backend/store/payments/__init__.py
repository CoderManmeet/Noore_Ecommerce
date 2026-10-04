"""
Payment provider seam (Phase G3).

One small interface (create a payment, verify the browser's return, handle a webhook) with
one implementation per provider. Which providers are offered is decided by
settings.ENABLED_PAYMENT_PROVIDERS; a provider that is not listed is refused everywhere,
even though its code stays in the project.

    from store.payments import get_provider, is_enabled
    get_provider("razorpay").create_payment(order)
"""

from django.conf import settings

RAZORPAY = "razorpay"
COD = "cod"
STRIPE = "stripe"
PAYPAL = "paypal"


class PaymentError(Exception):
    """A payment step could not be completed. `status` is the HTTP status to answer with."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


class ProviderNotEnabled(PaymentError):
    def __init__(self, name):
        super().__init__("This payment method is not available.", status=403)
        self.provider = name


def enabled_providers():
    return [str(name).lower() for name in settings.ENABLED_PAYMENT_PROVIDERS]


def is_enabled(name):
    return str(name).lower() in enabled_providers()


def require_enabled(name):
    if not is_enabled(name):
        raise ProviderNotEnabled(name)


def get_provider(name):
    """Return the provider object for `name`, or raise ProviderNotEnabled."""
    require_enabled(name)
    name = str(name).lower()
    if name == RAZORPAY:
        from store.payments.razorpay import RazorpayProvider

        return RazorpayProvider()
    if name in (STRIPE, PAYPAL):
        from store.payments.legacy import LegacyProvider

        return LegacyProvider(name)
    raise PaymentError(f"Unknown payment provider {name!r}.", status=400)
