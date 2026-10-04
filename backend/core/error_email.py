"""
Error reporting by email, with no third-party service.

Attached to the root logger when ERROR_REPORT_EMAILS is set. Each ERROR (or worse) is emailed
to those addresses. The record has already passed through core.logmask.PIIMaskingFilter, and
only the masked message and the traceback are sent: never the request body, headers, cookies
or settings (Django's own AdminEmailHandler includes those, which is why it is not used).

The same error is sent at most once every ERROR_REPORT_MIN_INTERVAL_SECONDS, so a failing
endpoint cannot flood the inbox. Sending never raises: a broken mail server must not turn one
error into two.
"""

import hashlib
import logging
import traceback

from django.conf import settings

from core.logmask import mask_pii


class ErrorEmailHandler(logging.Handler):
    def emit(self, record):
        try:
            self._send(record)
        except Exception:  # noqa: BLE001  (a logging handler must never raise)
            pass

    def _send(self, record):
        from django.core.cache import cache
        from django.core.mail import send_mail

        recipients = list(getattr(settings, "ERROR_REPORT_EMAILS", []) or [])
        if not recipients:
            return

        message = mask_pii(record.getMessage())
        trace = ""
        if record.exc_info:
            trace = mask_pii("".join(traceback.format_exception(*record.exc_info)))

        fingerprint = hashlib.sha256(f"{record.name}|{record.levelname}|{message[:200]}".encode()).hexdigest()[:32]
        key = f"error-email:{fingerprint}"
        # cache.add is atomic: only the first caller in the window gets True.
        if not cache.add(key, 1, timeout=settings.ERROR_REPORT_MIN_INTERVAL_SECONDS):
            return

        subject = f"[{settings.STORE_NAME}] {record.levelname} in {record.name}: {message[:80]}"
        body = (
            f"Logger: {record.name}\nLevel: {record.levelname}\nWhere: {record.pathname}:{record.lineno}\n\n"
            f"{message}\n\n{trace}\n"
            "Personal data is masked in this report. Repeats of this error are not emailed again for "
            f"{settings.ERROR_REPORT_MIN_INTERVAL_SECONDS} seconds."
        )
        send_mail(subject.replace("\n", " "), body, settings.SERVER_EMAIL, recipients, fail_silently=True)
