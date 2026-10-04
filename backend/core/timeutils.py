"""
Time helpers. The database stores UTC (USE_TZ=True). Business rules expressed in local
time (cutoffs, "12 hours", daily jobs) are evaluated in settings.BUSINESS_TIME_ZONE,
which defaults to Asia/Kolkata.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


class NaiveDatetimeError(ValueError):
    pass


def business_tz():
    return ZoneInfo(settings.BUSINESS_TIME_ZONE)


def now_utc():
    return timezone.now()


def require_aware(dt):
    if not isinstance(dt, datetime):
        raise TypeError("expected a datetime")
    if timezone.is_naive(dt):
        raise NaiveDatetimeError("naive datetimes are not allowed; attach a timezone")
    return dt


def to_business(dt):
    """Convert an aware datetime to the business timezone for display/rules."""
    return require_aware(dt).astimezone(business_tz())


def business_now():
    return timezone.now().astimezone(business_tz())


def business_today():
    return business_now().date()
