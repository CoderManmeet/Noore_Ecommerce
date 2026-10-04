"""
Health check for uptime monitors:  GET /api/v1/health/   (add ?strict=1 to also require the worker)

    200 {"status": "ok", ...}        the database and the cache answer
    503 {"status": "down", ...}      the database or the cache does not answer
    503 with ?strict=1               ...or the background worker has not finished a job recently

The worker matters: order emails, the Razorpay reconcile job and checkout-draft expiry all run
in it. It runs a periodic job every minute, so "no job finished for five minutes" means it is
not running. Nothing secret or personal is returned.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _database_ok():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False


def _cache_ok():
    try:
        cache.set("health-check", "1", timeout=30)
        return cache.get("health-check") == "1"
    except Exception:  # noqa: BLE001
        return False


def _worker_state():
    from core.models import Job

    try:
        last = Job.objects.filter(finished_at__isnull=False).order_by("-finished_at").values_list("finished_at", flat=True).first()
    except Exception:  # noqa: BLE001
        return {"ok": False, "seconds_since_last_job": None}
    if last is None:
        return {"ok": False, "seconds_since_last_job": None}
    age = int((timezone.now() - last).total_seconds())
    return {"ok": age <= settings.WORKER_STALE_AFTER_SECONDS, "seconds_since_last_job": age}


class HealthView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def get(self, request, *args, **kwargs):
        database = _database_ok()
        cache_works = _cache_ok() if database or settings.DJANGO_CACHE != "db" else False
        worker = _worker_state() if database else {"ok": False, "seconds_since_last_job": None}
        strict = request.GET.get("strict") == "1"

        healthy = database and cache_works and (worker["ok"] or not strict)
        body = {
            "status": "ok" if healthy else "down",
            "database": database,
            "cache": cache_works,
            "worker": worker,
        }
        return Response(body, status=200 if healthy else 503)
