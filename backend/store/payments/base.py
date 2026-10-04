"""The interface every payment provider implements."""

from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    name = ""

    @abstractmethod
    def create_payment(self, order):
        """Start a payment for the order's stored total. Returns what the browser needs."""

    @abstractmethod
    def verify_return(self, order, data):
        """Check what the browser brought back from the provider. Never marks an order paid."""

    @abstractmethod
    def handle_webhook(self, raw_body, headers):
        """Verify and act on a server-to-server notification. The only path that marks paid."""
