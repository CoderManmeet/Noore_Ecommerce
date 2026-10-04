"""
Stripe and PayPal, kept behind the provider seam (ROADMAP P12).

Their original views in store/views.py still do the work; this class only exists so that
`store.payments.get_provider("stripe")` answers consistently and so the views can be switched
off with ENABLED_PAYMENT_PROVIDERS. Neither is offered at checkout.
"""

from store.payments import PaymentError
from store.payments.base import PaymentProvider


class LegacyProvider(PaymentProvider):
    def __init__(self, name):
        self.name = name

    def create_payment(self, order):
        raise PaymentError(f"{self.name} payments are started through their original endpoint.", status=400)

    def verify_return(self, order, data):
        raise PaymentError(f"{self.name} returns are verified through /payment-success/.", status=400)

    def handle_webhook(self, raw_body, headers):
        raise PaymentError(f"{self.name} has no webhook in this project.", status=400)
