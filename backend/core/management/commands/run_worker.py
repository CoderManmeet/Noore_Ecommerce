import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from core.jobs import run_due_jobs, schedule_periodic

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the database-backed job worker (schedules periodic jobs and executes due jobs)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process one batch and exit (for cron / Task Scheduler).")
        parser.add_argument("--batch", type=int, default=50, help="Maximum jobs to run per loop.")
        parser.add_argument("--sleep", type=float, default=None, help="Seconds to sleep when idle.")

    def handle(self, *args, **options):
        sleep_seconds = options["sleep"] if options["sleep"] is not None else settings.JOB_WORKER_SLEEP_SECONDS
        batch = options["batch"]
        self.stdout.write(self.style.SUCCESS("worker started"))
        try:
            while True:
                schedule_periodic()
                ok, failed = run_due_jobs(limit=batch)
                if ok or failed:
                    self.stdout.write(f"ran {ok} ok, {failed} failed")
                if options["once"]:
                    break
                if ok + failed == 0:
                    time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            self.stdout.write("worker stopped")
