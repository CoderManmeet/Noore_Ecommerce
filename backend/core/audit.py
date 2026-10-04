"""
Audit trail helpers.

The "current actor" is kept in a context variable so that model signals and service
functions can attribute a change to whoever caused it without threading the request
through every call.  It is set by:

  * core.middleware.RequestActorMiddleware   (session users, e.g. Django admin)
  * core.authentication.AuditingJWTAuthentication  (API users authenticated by JWT)
  * core.audit.acting_as(...)                 (workers, management commands, tests)
"""

import contextvars
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

_current_actor = contextvars.ContextVar("core_current_actor", default=None)
_current_label = contextvars.ContextVar("core_current_actor_label", default="system")


def set_actor(user=None, label=None):
    """Set the actor for the current execution context."""
    if user is not None and getattr(user, "is_authenticated", False):
        _current_actor.set(user)
        _current_label.set(label or f"user:{user.pk}")
    else:
        _current_actor.set(None)
        _current_label.set(label or "anonymous")


def clear_actor():
    _current_actor.set(None)
    _current_label.set("system")


def get_actor():
    return _current_actor.get(), _current_label.get()


@contextmanager
def acting_as(user=None, label=None):
    """Temporarily attribute changes to `user` (or to a system label such as 'system:worker')."""
    actor_token = _current_actor.set(user if (user is not None and getattr(user, "is_authenticated", False)) else None)
    if label is None:
        label = f"user:{user.pk}" if user is not None and getattr(user, "is_authenticated", False) else "system"
    label_token = _current_label.set(label)
    try:
        yield
    finally:
        _current_actor.reset(actor_token)
        _current_label.reset(label_token)


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "pk"):
        return value.pk
    return str(value)


def snapshot(instance, fields):
    """Return a JSON-safe dict of the given field values (FKs stored as their pk)."""
    data = {}
    for name in fields:
        field = instance._meta.get_field(name)
        attname = getattr(field, "attname", name)
        data[name] = _jsonable(getattr(instance, attname))
    return data


def record(action, instance, before=None, after=None, reason="", actor=None, actor_label=None):
    """Write one append-only AuditLog row for `instance`."""
    from core.models import AuditLog

    ctx_actor, ctx_label = get_actor()
    if actor is None:
        actor = ctx_actor
    if actor_label is None:
        if actor is not None and actor is not ctx_actor:
            actor_label = f"user:{actor.pk}"
        else:
            actor_label = ctx_label
    return AuditLog.objects.create(
        actor=actor,
        actor_label=actor_label[:100],
        action=action[:100],
        content_type=ContentType.objects.get_for_model(type(instance)),
        object_id=str(instance.pk),
        object_repr=str(instance)[:200],
        before=before,
        after=after,
        reason=(reason or "")[:255],
    )
