"""
Database-backed job outbox.

    from core.jobs import job, enqueue

    @job("cod.send_confirmation")
    def send_cod_confirmation(payload):
        ...  # must be idempotent

    enqueue("cod.send_confirmation", {"order_id": 5}, dedupe_key="cod-confirm:5")

Periodic jobs are registered with @periodic(name, every_seconds=...). The worker enqueues
them with a time-bucketed dedupe key, so running two workers never double-schedules.

Claiming uses a conditional UPDATE (status PENDING -> RUNNING for one id), which is atomic
on both SQLite and PostgreSQL, so two workers can never run the same job concurrently.

Delivery is at-least-once: a worker that crashes mid-job leaves the row RUNNING until the
stale-job reaper returns it to PENDING. Every handler must therefore be idempotent.
"""

import logging
import os
import socket
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from core.audit import acting_as
from core.logmask import mask_pii
from core.models import Job

logger = logging.getLogger(__name__)

_HANDLERS = {}
_PERIODIC = {}


class UnknownJobError(LookupError):
    pass


def job(name):
    def decorator(func):
        if name in _HANDLERS and _HANDLERS[name] is not func:
            raise ValueError(f"job {name!r} is already registered")
        _HANDLERS[name] = func
        return func

    return decorator


def periodic(name, every_seconds):
    if every_seconds < 1:
        raise ValueError("every_seconds must be >= 1")

    def decorator(func):
        job(name)(func)
        _PERIODIC[name] = int(every_seconds)
        return func

    return decorator


def registered_jobs():
    return dict(_HANDLERS)


def registered_periodic():
    return dict(_PERIODIC)


def enqueue(name, payload=None, run_after=None, dedupe_key=None, max_attempts=None):
    """
    Enqueue a job. With a dedupe_key the call is idempotent: a second call with the same key
    returns the existing job (whatever its status) and creates nothing.
    Returns (job, created).
    """
    if name not in _HANDLERS:
        raise UnknownJobError(f"no handler registered for job {name!r}")
    if run_after is not None and timezone.is_naive(run_after):
        raise ValueError("run_after must be timezone-aware")
    fields = {
        "name": name,
        "payload": payload or {},
        "run_after": run_after or timezone.now(),
        "max_attempts": max_attempts or settings.JOB_MAX_ATTEMPTS,
    }
    if dedupe_key is None:
        return Job.objects.create(**fields), True
    try:
        with transaction.atomic():
            return Job.objects.create(dedupe_key=dedupe_key, **fields), True
    except IntegrityError:
        return Job.objects.get(dedupe_key=dedupe_key), False


def schedule_periodic(now=None):
    """Enqueue one occurrence of each periodic job for the current time bucket."""
    now = now or timezone.now()
    created = 0
    epoch = int(now.timestamp())
    for name, every in _PERIODIC.items():
        bucket = epoch // every
        _, was_created = enqueue(name, {"bucket": bucket}, dedupe_key=f"periodic:{name}:{bucket}")
        created += int(was_created)
    return created


def _worker_id():
    return f"{socket.gethostname()}:{os.getpid()}"[:100]


def _claim(job_id, worker_id):
    now = timezone.now()
    claimed = Job.objects.filter(pk=job_id, status=Job.STATUS_PENDING).update(
        status=Job.STATUS_RUNNING, locked_at=now, locked_by=worker_id, attempts=F("attempts") + 1
    )
    return claimed == 1


def _backoff_seconds(attempts):
    return min(60 * (2 ** max(attempts - 1, 0)), 3600)


def run_job(job_row):
    """Execute one claimed job row and record the outcome."""
    handler = _HANDLERS.get(job_row.name)
    job_row.refresh_from_db()
    if handler is None:
        Job.objects.filter(pk=job_row.pk).update(
            status=Job.STATUS_DEAD, last_error=f"no handler registered for {job_row.name}", finished_at=timezone.now()
        )
        logger.error("job %s#%s has no handler; marked DEAD", job_row.name, job_row.pk)
        return False
    try:
        with acting_as(None, label="system:worker"):
            handler(job_row.payload)
    except Exception:
        error = mask_pii(traceback.format_exc())[-4000:]
        if job_row.attempts >= job_row.max_attempts:
            Job.objects.filter(pk=job_row.pk).update(
                status=Job.STATUS_DEAD, last_error=error, locked_at=None, locked_by="", finished_at=timezone.now()
            )
            logger.error("job %s#%s failed permanently after %s attempts", job_row.name, job_row.pk, job_row.attempts)
        else:
            Job.objects.filter(pk=job_row.pk).update(
                status=Job.STATUS_PENDING,
                last_error=error,
                locked_at=None,
                locked_by="",
                run_after=timezone.now() + timedelta(seconds=_backoff_seconds(job_row.attempts)),
            )
            logger.warning("job %s#%s failed (attempt %s); will retry", job_row.name, job_row.pk, job_row.attempts)
        return False
    Job.objects.filter(pk=job_row.pk).update(
        status=Job.STATUS_DONE, locked_at=None, locked_by="", last_error="", finished_at=timezone.now()
    )
    return True


def run_due_jobs(limit=50, worker_id=None):
    """Claim and run up to `limit` due jobs. Returns (succeeded, failed)."""
    worker_id = worker_id or _worker_id()
    due_ids = list(
        Job.objects.filter(status=Job.STATUS_PENDING, run_after__lte=timezone.now())
        .order_by("run_after", "id")
        .values_list("id", flat=True)[:limit]
    )
    ok = failed = 0
    for job_id in due_ids:
        if not _claim(job_id, worker_id):
            continue
        row = Job.objects.get(pk=job_id)
        if run_job(row):
            ok += 1
        else:
            failed += 1
    return ok, failed


def reap_stale_jobs(stale_after_seconds=None):
    """Return RUNNING jobs whose worker vanished back to PENDING. Returns the count."""
    stale_after_seconds = stale_after_seconds or settings.JOB_STALE_AFTER_SECONDS
    cutoff = timezone.now() - timedelta(seconds=stale_after_seconds)
    return Job.objects.filter(status=Job.STATUS_RUNNING, locked_at__lt=cutoff).update(
        status=Job.STATUS_PENDING, locked_at=None, locked_by=""
    )
