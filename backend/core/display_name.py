"""
Public display names.

A shopper's stored name is not safe to print. `User.save()` falls back to the email
address when `full_name` is blank (that is how a `createsuperuser` account ends up
called "someone@gmail.com"), and `Profile.save()` copies that value onward. Anything
that renders a reviewer's name to other shoppers must go through `public_display_name`,
which refuses to return an email address or a phone number.

Rules, in order:

1. The first candidate that is a real name is used as given.
2. A candidate that is an email address contributes only its local part
   ("manmeet0000@gmail.com" -> "Manmeet0000"), which is the same value the project
   already stores in `User.username`.
3. A candidate that looks like a phone number is discarded entirely.
4. If nothing survives, `FALLBACK_DISPLAY_NAME` is returned.

The functions take strings, not model instances, so this module stays importable from
anywhere (including `core.serializers`) without touching the ORM.
"""

import re

FALLBACK_DISPLAY_NAME = "Verified buyer"

# Longest name we will print. Long enough for a full Indian name, short enough that a
# pasted sentence cannot become a byline.
MAX_DISPLAY_NAME = 40

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DIGITS_RE = re.compile(r"\d")
_SEPARATORS_RE = re.compile(r"[._\-+]+")


def looks_like_email(value):
    """True when the whole string is a single email address."""
    if not value:
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def looks_like_phone(value):
    """True when the string is mostly digits, i.e. a phone number rather than a name."""
    if not value:
        return False
    stripped = re.sub(r"[\s()+\-.]", "", value.strip())
    if not stripped:
        return False
    return stripped.isdigit() and len(stripped) >= 6


def _from_email_local_part(value):
    """"manmeet.singh00@gmail.com" -> "Manmeet Singh00"."""
    local_part = value.strip().split("@", 1)[0]
    words = [word for word in _SEPARATORS_RE.split(local_part) if word]
    if not words:
        return ""
    # Only capitalise the first letter; never lowercase the rest, so "MSingh" survives.
    return " ".join(word[:1].upper() + word[1:] for word in words)


def clean_candidate(value):
    """
    Turn one stored value into something printable, or "" if it cannot be printed.

    Never returns a string containing "@".
    """
    if not value:
        return ""
    value = " ".join(str(value).split())
    if not value:
        return ""
    if looks_like_phone(value):
        return ""
    if looks_like_email(value):
        value = _from_email_local_part(value)
    elif "@" in value:
        # Not a clean address (e.g. "Manmeet <me@x.com>"); drop everything from the "@"
        # and keep whatever readable text came first.
        value = value.split("@", 1)[0].strip(" <>.,;:")
    if not value:
        return ""
    if looks_like_phone(value):
        return ""
    if _DIGITS_RE.sub("", value).strip() == "" and len(value) >= 6:
        # All digits with punctuation removed: a phone number in disguise.
        return ""
    return value[:MAX_DISPLAY_NAME].strip()


def public_display_name(*candidates):
    """
    First printable name among `candidates`, else FALLBACK_DISPLAY_NAME.

    Pass them in order of preference, e.g.
    `public_display_name(profile.full_name, user.full_name, user.username)`.
    """
    for candidate in candidates:
        cleaned = clean_candidate(candidate)
        if cleaned:
            return cleaned
    return FALLBACK_DISPLAY_NAME


def display_name_for_user(user, profile=None):
    """Convenience wrapper for a User (and optionally their Profile)."""
    candidates = []
    if profile is not None:
        candidates.append(getattr(profile, "full_name", None))
    if user is not None:
        candidates.append(getattr(user, "full_name", None))
        candidates.append(getattr(user, "username", None))
    return public_display_name(*candidates)