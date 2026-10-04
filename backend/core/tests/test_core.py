from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from core import jobs as jobs_module
from core.audit import acting_as
from core.idempotency import claim_event, is_processed
from core.jobs import enqueue, job, reap_stale_jobs, run_due_jobs, schedule_periodic, periodic
from core.logmask import mask_pii
from core.models import AppendOnlyError, AuditLog, Job, ProcessedEvent
from core.money import MoneyError, format_inr, from_paise, to_paise
from core.timeutils import NaiveDatetimeError, business_tz, to_business

CALLS = []


@job("tests.record_call")
def _record_call(payload):
    CALLS.append(payload)


@job("tests.always_fails")
def _always_fails(payload):
    raise RuntimeError("boom for 9876543210 and asha@example.com")


@periodic("tests.every_minute", every_seconds=60)
def _every_minute(payload):
    CALLS.append(("periodic", payload))


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()
    yield
    CALLS.clear()


# ---------------------------------------------------------------- audit

def _audit_rows(instance):
    return AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(type(instance)), object_id=str(instance.pk)
    )


@pytest.mark.django_db
def test_price_change_writes_exactly_one_audit_row_with_before_and_after(product, staff):
    baseline = _audit_rows(product).count()
    with acting_as(staff):
        product.price = Decimal("49.00")
        product.save()
    rows = _audit_rows(product).order_by("id")
    assert rows.count() == baseline + 1
    row = rows.last()
    assert row.action == "product.updated"
    assert row.before == {"price": "56.00"}
    assert row.after == {"price": "49.00"}
    assert row.actor_id == staff.id
    assert row.actor_label == f"user:{staff.id}"


@pytest.mark.django_db
def test_save_without_tracked_change_writes_no_audit_row(product):
    baseline = _audit_rows(product).count()
    product.title = "Renamed"
    product.save()
    assert _audit_rows(product).count() == baseline


@pytest.mark.django_db
def test_order_status_change_is_audited_as_system_when_no_user(make_order):
    order = make_order()
    order.payment_status = "paid"
    order.save()
    row = _audit_rows(order).filter(action="order.updated").get()
    assert row.before["payment_status"] == "processing"
    assert row.after["payment_status"] == "paid"
    assert row.actor is None


@pytest.mark.django_db
def test_api_change_is_attributed_to_the_jwt_user(auth, customer, vendor, make_order, product):
    from store.models import CartOrderItem, Coupon

    order = make_order(buyer=customer, total=Decimal("100.00"))
    CartOrderItem.objects.create(order=order, product=product, qty=1, price=Decimal("100.00"),
                                 sub_total=Decimal("100.00"), total=Decimal("100.00"), vendor=vendor)
    Coupon.objects.create(vendor=vendor, code="SAVE10", discount=10, active=True)

    response = auth(customer).post("/api/v1/coupon/", {"order_oid": order.oid, "coupon_code": "SAVE10"})
    assert response.status_code == 200
    row = _audit_rows(order).filter(action="order.updated").latest("id")
    assert row.actor_id == customer.id
    # G1: the coupon takes 10% off the Rs 100 subtotal and the order now carries the flat
    # Rs 79 shipping from store.pricing.quote(): 100 - 10 + 79 = Rs 169. `total_paise` is a
    # tracked field alongside its Decimal mirror.
    assert row.before == {"total": "100.00", "total_paise": 10000}
    assert row.after == {"total": "169.00", "total_paise": 16900}


@pytest.mark.django_db
def test_audit_log_is_append_only(product):
    row = _audit_rows(product).first()
    row.reason = "tamper"
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=row.pk).update(reason="tamper")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()


# ---------------------------------------------------------------- idempotency

@pytest.mark.django_db
def test_event_can_be_claimed_exactly_once():
    assert claim_event("razorpay", "evt_1") is True
    assert claim_event("razorpay", "evt_1") is False
    assert claim_event("whatsapp", "evt_1") is True
    assert is_processed("razorpay", "evt_1")
    assert ProcessedEvent.objects.count() == 2


# ---------------------------------------------------------------- jobs

@pytest.mark.django_db
def test_enqueue_with_dedupe_key_creates_one_job_and_runs_it_once():
    first, created_first = enqueue("tests.record_call", {"n": 1}, dedupe_key="k1")
    second, created_second = enqueue("tests.record_call", {"n": 2}, dedupe_key="k1")
    assert created_first and not created_second
    assert first.pk == second.pk
    assert run_due_jobs() == (1, 0)
    assert run_due_jobs() == (0, 0)
    assert CALLS == [{"n": 1}]
    assert Job.objects.get(pk=first.pk).status == Job.STATUS_DONE


@pytest.mark.django_db
def test_job_is_not_run_before_run_after():
    enqueue("tests.record_call", {"n": 1}, run_after=timezone.now() + timedelta(hours=1))
    assert run_due_jobs() == (0, 0)
    assert CALLS == []


@pytest.mark.django_db
def test_naive_run_after_is_rejected():
    with pytest.raises(ValueError):
        enqueue("tests.record_call", {}, run_after=datetime(2030, 1, 1, 12, 0))


@pytest.mark.django_db
def test_a_job_cannot_be_claimed_twice():
    row, _ = enqueue("tests.record_call", {"n": 1})
    assert jobs_module._claim(row.pk, "worker-a") is True
    assert jobs_module._claim(row.pk, "worker-b") is False


@pytest.mark.django_db
def test_failing_job_retries_with_backoff_then_goes_dead_with_masked_error():
    row, _ = enqueue("tests.always_fails", {}, max_attempts=2)
    assert run_due_jobs() == (0, 1)
    row.refresh_from_db()
    assert row.status == Job.STATUS_PENDING
    assert row.attempts == 1
    assert row.run_after > timezone.now()

    Job.objects.filter(pk=row.pk).update(run_after=timezone.now())
    assert run_due_jobs() == (0, 1)
    row.refresh_from_db()
    assert row.status == Job.STATUS_DEAD
    assert "9876543210" not in row.last_error
    assert "asha@example.com" not in row.last_error


@pytest.mark.django_db
def test_periodic_scheduling_is_idempotent_within_a_bucket():
    now = timezone.now()
    schedule_periodic(now)
    schedule_periodic(now)
    assert Job.objects.filter(name="tests.every_minute").count() == 1


@pytest.mark.django_db
def test_stale_running_jobs_are_reclaimed():
    row, _ = enqueue("tests.record_call", {"n": 1})
    Job.objects.filter(pk=row.pk).update(status=Job.STATUS_RUNNING, locked_at=timezone.now() - timedelta(hours=1))
    assert reap_stale_jobs(stale_after_seconds=60) == 1
    assert run_due_jobs() == (1, 0)


@pytest.mark.django_db
def test_run_worker_once_command_processes_due_jobs():
    enqueue("tests.record_call", {"n": 7})
    call_command("run_worker", "--once")
    assert {"n": 7} in CALLS


# ---------------------------------------------------------------- money

def test_to_paise_is_exact_and_rejects_float():
    assert to_paise(Decimal("56.00")) == 5600
    assert to_paise("0.10") == 10
    assert to_paise(Decimal("1.005")) == 101
    assert to_paise(12) == 1200
    with pytest.raises(MoneyError):
        to_paise(0.1)
    with pytest.raises(MoneyError):
        to_paise("abc")


def test_from_paise_and_format():
    assert from_paise(5600) == Decimal("56.00")
    assert from_paise(-5) == Decimal("-0.05")
    assert format_inr(123456) == "₹1,234.56"
    with pytest.raises(MoneyError):
        from_paise(56.0)


# ---------------------------------------------------------------- time

def test_business_time_is_asia_kolkata_and_naive_is_rejected():
    assert str(business_tz()) == "Asia/Kolkata"
    utc_noon = datetime(2026, 9, 27, 12, 0, tzinfo=dt_timezone.utc)
    local = to_business(utc_noon)
    assert (local.hour, local.minute) == (17, 30)
    with pytest.raises(NaiveDatetimeError):
        to_business(datetime(2026, 9, 27, 12, 0))


# ---------------------------------------------------------------- log masking

def test_log_masking_hides_pii_and_tokens():
    raw = ("user asha.rao@example.com phone +91 98765 43210 "
           "token eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxfQ.abcdefghij Bearer abc.def.ghi")
    masked = mask_pii(raw)
    assert "asha.rao@example.com" not in masked
    assert "98765 43210" not in masked
    assert "***3210" in masked
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert "Bearer [token]" in masked
