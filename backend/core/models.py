from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AppendOnlyError(Exception):
    """Raised when code tries to modify or delete an append-only record."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError(f"{self.model.__name__} rows are append-only; update() is not allowed.")

    def delete(self):
        raise AppendOnlyError(f"{self.model.__name__} rows are append-only; delete() is not allowed.")


class AppendOnlyModel(models.Model):
    """Base for tables that may only ever receive INSERTs."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise AppendOnlyError(f"{type(self).__name__} rows are append-only; existing rows cannot be saved.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError(f"{type(self).__name__} rows are append-only; delete() is not allowed.")


class AuditLog(AppendOnlyModel):
    """
    Append-only record of every audited state change.

    actor is the authenticated user who caused the change (null for system/anonymous);
    actor_label always carries a human-readable origin such as "user:12", "anonymous",
    "system:worker" or "system:signal".
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    actor_label = models.CharField(max_length=100)
    action = models.CharField(max_length=100, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="+")
    object_id = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=200, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["content_type", "object_id", "created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.actor_label} {self.action} {self.object_repr}"


class ProcessedEvent(AppendOnlyModel):
    """
    Idempotency ledger for inbound webhooks and verified external confirmations.

    A (provider, event_id) pair can be claimed exactly once; any later attempt to
    claim it is a duplicate and must be short-circuited by the caller.
    """

    provider = models.CharField(max_length=50)
    event_id = models.CharField(max_length=255)
    received_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="core_processedevent_provider_event_uniq"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"


class Job(models.Model):
    """
    Database-backed job outbox processed by `python manage.py run_worker`.

    dedupe_key, when set, is unique: enqueueing the same logical job twice returns the
    existing row instead of creating a second one.
    """

    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_DEAD = "DEAD"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_DEAD, "Dead"),
    )

    name = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    run_after = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    last_error = models.TextField(blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["run_after", "id"]
        indexes = [models.Index(fields=["status", "run_after"])]

    def __str__(self):
        return f"{self.name}#{self.pk} [{self.status}]"
