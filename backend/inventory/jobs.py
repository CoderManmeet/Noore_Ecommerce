"""Periodic inventory jobs, run by `python manage.py run_worker`."""

import logging

from core.jobs import periodic
from inventory.services import expire_due_reservations

logger = logging.getLogger(__name__)


@periodic("inventory.expire_reservations", every_seconds=60)
def expire_reservations_job(payload):
    """Release stock held by abandoned checkouts. Idempotent: expiring twice is a no-op."""
    released = expire_due_reservations()
    if released:
        logger.info("expired %s stock reservation(s)", released)
