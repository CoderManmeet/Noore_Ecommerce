"""Built-in periodic jobs owned by the core app."""

import logging

from core.jobs import periodic, reap_stale_jobs

logger = logging.getLogger(__name__)


@periodic("core.reap_stale_jobs", every_seconds=300)
def reap_stale_jobs_job(payload):
    count = reap_stale_jobs()
    if count:
        logger.warning("returned %s stale RUNNING job(s) to PENDING", count)
