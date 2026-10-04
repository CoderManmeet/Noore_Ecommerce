"""
Run the background jobs from an HTTP request (Phase G5, free hosting).

    POST /api/v1/jobs/run/      header:  X-Jobs-Token: <JOBS_RUN_TOKEN>

Order emails, Razorpay reconciliation and checkout expiry live in `manage.py run_worker`. Some
hosting (free tiers in particular) cannot run a second process, so this endpoint does one batch
of the same work. Point any scheduler at it: a GitHub Actions workflow, cron-job.org, or
Windows Task Scheduler.

It is off unless `JOBS_RUN_TOKEN` is set, and then it answers 404 to anyone without the token,
so the address gives nothing away. The token is compared in constant time and is never logged.
Running it twice at once is safe: each job is claimed by one runner only.
"""

import hmac
import logging

from django.conf import settings
from django.http import Http404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.jobs import run_due_jobs, schedule_periodic

logger = logging.getLogger(__name__)


class RunJobsView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def post(self, request, *args, **kwargs):
        expected = settings.JOBS_RUN_TOKEN
        supplied = request.headers.get("X-Jobs-Token", "")
        if not expected or not hmac.compare_digest(str(expected), str(supplied)):
            # Nothing is revealed: no token configured and a wrong token look identical.
            raise Http404

        schedule_periodic()
        ok, failed = run_due_jobs(limit=settings.JOBS_RUN_BATCH)
        if ok or failed:
            logger.info("jobs run over http: %s ok, %s failed", ok, failed)
        return Response({"ran": ok, "failed": failed})