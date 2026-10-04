"""
What the storefront may honestly say about a variant's price and stock.

Both functions exist so that no page invents a claim: a strike-through is only shown when
the data supports it, and "Only N left" is only shown when N is the real available quantity
(CLAUDE.md section 8: no false urgency, no fake scarcity).
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from catalog.models import PriceHistory
from inventory.services import available_qty

IN_STOCK = "in_stock"
LOW_STOCK = "low_stock"
SOLD_OUT = "sold_out"


def _percent_off(price_paise, compare_at_paise):
    """Whole percent, rounded DOWN so a discount is never overstated."""
    return (compare_at_paise - price_paise) * 100 // compare_at_paise


def lowest_prior_price(variant, now=None):
    """
    The lowest selling price that was in force during the PRICE_HISTORY_WINDOW_DAYS before the
    current price took effect, or None when there is no earlier price on record.
    """
    now = now or timezone.now()
    history = list(
        PriceHistory.objects.filter(variant=variant, effective_from__lte=now).order_by("effective_from", "id")
    )
    if not history:
        return None
    # Consecutive rows with the same selling price (an MRP-only edit) belong to the same
    # price period, so the current price took effect at the first row of that period.
    current_index = len(history) - 1
    while current_index > 0 and history[current_index - 1].price_paise == history[current_index].price_paise:
        current_index -= 1
    current = history[current_index]
    window_start = current.effective_from - timedelta(days=settings.PRICE_HISTORY_WINDOW_DAYS)

    earlier = history[:current_index]
    in_window = [row for row in earlier if row.effective_from >= window_start]
    before_window = [row for row in earlier if row.effective_from < window_start]
    if before_window:
        # The price already in force when the window opened also applied inside the window.
        in_window.append(before_window[-1])
    if not in_window:
        return None
    return min(row.price_paise for row in in_window)


def strikethrough_for(variant, now=None):
    """
    The struck-through "was" price for a variant, or None when none may be shown.

    Flag off (default): MRP against selling price, whenever mrp_paise > price_paise.
    Flag on (STRIKETHROUGH_REQUIRES_PRICE_HISTORY): only when the lowest price in the window
    before the current price took effect was higher than the current price; that lowest
    price is the one struck through. No discount is ever claimed without data behind it.
    """
    price = int(variant.price_paise)
    if settings.STRIKETHROUGH_REQUIRES_PRICE_HISTORY:
        compare_at = lowest_prior_price(variant, now=now)
        basis = "price_history"
    else:
        compare_at = variant.mrp_paise
        basis = "mrp"
    if compare_at is None or int(compare_at) <= price or int(compare_at) <= 0:
        return None
    compare_at = int(compare_at)
    return {"compare_at_paise": compare_at, "percent_off": _percent_off(price, compare_at), "basis": basis}


def stock_status(variant, available=None):
    """
    {"state", "label", "left"} from the stock ledger.

    "Only N left" is used only when N is the real available quantity and is at or below
    LOW_STOCK_THRESHOLD; `left` is None otherwise, so the exact count is never used as a
    pressure tactic above the threshold.

    `available` lets a caller that has already read the whole page's stock pass it in
    (inventory.services.available_qty_map); the number means exactly the same thing.
    """
    if available is None:
        available = available_qty(variant)
    if available <= 0:
        return {"state": SOLD_OUT, "label": "Sold out", "left": 0}
    if available <= settings.LOW_STOCK_THRESHOLD:
        return {"state": LOW_STOCK, "label": f"Only {available} left", "left": available}
    return {"state": IN_STOCK, "label": "In stock", "left": None}