"""
Money helpers. All new code stores and computes money as integer paise.

Legacy tables still hold Decimal rupees (see docs/BUILD_LOG.md, "Money migration");
convert at the boundary with to_paise() / from_paise(). Floats are rejected outright.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISE_PER_RUPEE = 100


class MoneyError(ValueError):
    pass


def to_paise(amount):
    """Convert rupees (Decimal, int or numeric str) to integer paise, rounding half-up."""
    if isinstance(amount, bool):
        raise MoneyError("bool is not a money value")
    if isinstance(amount, float):
        raise MoneyError("float is not allowed for money; pass Decimal, int or str")
    if isinstance(amount, int):
        return amount * PAISE_PER_RUPEE
    try:
        value = Decimal(str(amount).strip())
    except (InvalidOperation, AttributeError):
        raise MoneyError(f"not a valid money amount: {amount!r}")
    if not value.is_finite():
        raise MoneyError(f"not a finite money amount: {amount!r}")
    return int((value * PAISE_PER_RUPEE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_paise(paise):
    """Convert integer paise to Decimal rupees with exactly two decimal places."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise MoneyError("paise must be an int")
    return (Decimal(paise) / PAISE_PER_RUPEE).quantize(Decimal("0.01"))


def format_inr(paise):
    """Human display, e.g. 123456 -> '₹1,234.56' (Western grouping; Indian grouping is a UI concern)."""
    rupees = from_paise(paise)
    sign = "-" if rupees < 0 else ""
    return f"{sign}₹{abs(rupees):,.2f}"
