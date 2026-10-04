"""
Phone number normalisation to E.164 for India.

WhatsApp and SMS providers require +91XXXXXXXXXX. The existing `phone` and `mobile`
columns are free text (users typed spaces, dashes, 0 prefixes and +91 in every
combination), so every outbound message path normalises through here first.

Deliberately narrow: it accepts Indian mobile numbers and rejects anything else rather
than guessing. `mask()` is what may appear in logs.
"""

import re

DIGITS = re.compile(r"\D")
INDIA_CC = "91"
# Indian mobile numbers are 10 digits starting 6-9.
INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")


class InvalidPhoneNumber(ValueError):
    pass


def to_e164(raw, default_country_code=INDIA_CC):
    """Return +91XXXXXXXXXX, or raise InvalidPhoneNumber."""
    if not raw:
        raise InvalidPhoneNumber("No phone number supplied.")
    digits = DIGITS.sub("", str(raw))

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith(default_country_code) and len(digits) == len(default_country_code) + 10:
        digits = digits[len(default_country_code):]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if not INDIAN_MOBILE.match(digits):
        raise InvalidPhoneNumber(f"Not a valid Indian mobile number: {mask(raw)}")
    return f"+{default_country_code}{digits}"


def try_to_e164(raw, default_country_code=INDIA_CC):
    """Same as to_e164 but returns "" instead of raising. Use where a phone is optional."""
    try:
        return to_e164(raw, default_country_code)
    except InvalidPhoneNumber:
        return ""


def mask(raw):
    """Log-safe form: last four digits only."""
    digits = DIGITS.sub("", str(raw or ""))
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"
