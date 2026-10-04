"""
PII masking for log output. Attach PIIMaskingFilter to every handler.

Masks: email addresses, Indian/E.164-style phone numbers (10+ digits), long card-like
digit runs, and Bearer/JWT tokens. Applied to the fully formatted message so it covers
f-strings, %-args and exception text alike.
"""

import logging
import re

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{8,}\d)(?!\d)")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._-]+", re.IGNORECASE)


def _mask_phone(match):
    digits = re.sub(r"\D", "", match.group(1))
    if len(digits) < 10:
        return match.group(1)
    return f"***{digits[-4:]}"


def mask_pii(text):
    if not text:
        return text
    text = JWT_RE.sub("[jwt]", text)
    text = BEARER_RE.sub(r"\1[token]", text)
    text = EMAIL_RE.sub(r"\1***@\2", text)
    text = PHONE_RE.sub(_mask_phone, text)
    return text


class PIIMaskingFilter(logging.Filter):
    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True
        masked = mask_pii(message)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = mask_pii(record.exc_text)
        record.msg = masked
        record.args = ()
        return True
