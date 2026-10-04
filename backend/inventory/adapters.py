"""
Channel adapter seam.

Stock is channel-agnostic: the ledger records which channel caused each movement, and
nothing in the business logic assumes an order came from our own checkout.

Only the WEBSITE adapter is implemented. Marketplace and quick-commerce adapters are
deliberately NOT built - this module exists so one can be added later without a rewrite.
A new adapter subclasses ChannelAdapter, is registered with @register_adapter, and calls
the same inventory.services functions; it must not touch StockMovement directly.
"""

from inventory.models import Channel
from inventory.services import available_qty, consume_for_order, release_for_order, reserve

_ADAPTERS = {}


class ChannelAdapter:
    """Interface every sales channel implements."""

    channel = None

    def available(self, variant):
        """Units this channel may currently sell."""
        raise NotImplementedError

    def reserve(self, variant, quantity, **kwargs):
        """Hold stock for an in-progress order on this channel."""
        raise NotImplementedError

    def confirm(self, order, **kwargs):
        """Turn holds into a physical stock-out for a dispatched order."""
        raise NotImplementedError

    def cancel(self, order, **kwargs):
        """Give held stock back."""
        raise NotImplementedError


def register_adapter(cls):
    if cls.channel is None:
        raise ValueError("A channel adapter must declare `channel`.")
    _ADAPTERS[cls.channel] = cls
    return cls


def get_adapter(channel):
    try:
        return _ADAPTERS[channel]()
    except KeyError:
        raise LookupError(
            f"No stock adapter is registered for channel {channel!r}. "
            "Marketplace and quick-commerce adapters are intentionally not implemented."
        )


def registered_channels():
    return sorted(_ADAPTERS)


@register_adapter
class WebsiteChannelAdapter(ChannelAdapter):
    """Our own storefront. The only implemented adapter."""

    channel = Channel.WEBSITE

    def available(self, variant):
        return available_qty(variant)

    def reserve(self, variant, quantity, **kwargs):
        return reserve(variant, quantity, **kwargs)

    def confirm(self, order, **kwargs):
        return consume_for_order(order, channel=self.channel, **kwargs)

    def cancel(self, order, **kwargs):
        return release_for_order(order, **kwargs)
