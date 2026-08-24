"""Scheduled-task overdue detection - shared, scheduler-truth, grace-bounded.

Covers UAC OBS-S2-01 .. OBS-S2-11.

Why this file exists: "overdue" was previously computed twice, from a column the
scheduler does not obey.

- `app/api/v1/system/health.py` counted `next_run_at IS NULL OR next_run_at < now`.
- `app/services/system_health_alert_service.py` counted `next_run_at < now`,
  deliberately excluding NULL.

So the dashboard card and the alert email could disagree about the same DB state,
and both disagreed with the scheduler, whose real due-check is frequency-based on
`last_run_at` (`_is_task_due`). `compute_next_run` is documented display-only.

These tests pin a single shared helper used by both surfaces, derived from
`last_run_at + interval`, with a bounded grace period so ordinary jitter stops
producing alert emails.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.scheduled_task import ScheduledTask
from app.services import scheduled_task_service as svc
from tests._pg_fixture import blank_session


# The old fixture rewrote ScheduledTask's JSONB/ARRAY columns to JSON in place so
# they would emit on sqlite. That edit was permanent and process-wide -- it
# altered the model for every test that ran afterwards. On Postgres the real
# column types work as declared, so the mutation is gone.
@pytest.fixture
def db():
    with blank_session() as session:
        yield session


NOW = datetime(2026, 7, 1, 12, 0, 0)


def _task(
    db,
    *,
    key="t",
    enabled=True,
    interval_unit="minutes",
    interval_value=10,
    last_run_at=None,
    start_at=None,
    next_run_at=None,
    created_at=None,
    metadata_=None,
):
    t = ScheduledTask(
        id=str(uuid.uuid4()),
        key=key,
        name=key.replace("_", " ").title(),
        enabled=enabled,
        interval_unit=interval_unit,
        interval_value=interval_value,
        last_run_at=last_run_at,
        start_at=start_at,
        next_run_at=next_run_at,
        created_at=created_at or (NOW - timedelta(days=7)),
        metadata_=metadata_,
    )
    db.add(t)
    db.commit()
    return t


# --------------------------------------------------------------------------- #
# OBS-S2-01 - due_at derives from scheduler truth, never next_run_at           #
# --------------------------------------------------------------------------- #
def test_due_at_is_last_run_plus_interval(db):
    t = _task(db, last_run_at=NOW - timedelta(minutes=30), interval_value=10)
    assert svc.compute_due_at(t) == (NOW - timedelta(minutes=30)) + timedelta(minutes=10)


def test_due_at_ignores_next_run_at_entirely(db):
    """next_run_at is display-only; poisoning it must not move due_at."""
    t = _task(
        db,
        last_run_at=NOW - timedelta(minutes=30),
        interval_value=10,
        next_run_at=NOW + timedelta(days=365),
    )
    assert svc.compute_due_at(t) == (NOW - timedelta(minutes=30)) + timedelta(minutes=10)


# --------------------------------------------------------------------------- #
# OBS-S2-02 - never-run task is due, not silently skipped                      #
# --------------------------------------------------------------------------- #
def test_never_run_with_past_start_at_is_due_at_start_at(db):
    start = NOW - timedelta(hours=2)
    t = _task(db, last_run_at=None, start_at=start)
    assert svc.compute_due_at(t) == start


def test_never_run_without_start_at_falls_back_to_created_at(db):
    created = NOW - timedelta(hours=5)
    t = _task(db, last_run_at=None, start_at=None, created_at=created)
    assert svc.compute_due_at(t) == created


def test_never_run_task_is_reported_overdue(db):
    """The watchdog previously excluded NULL next_run_at, hiding stuck new tasks."""
    _task(db, key="never_ran", last_run_at=None, created_at=NOW - timedelta(days=1))
    keys = [o.task.key for o in svc.get_overdue_tasks(db, NOW)]
    assert "never_ran" in keys


# --------------------------------------------------------------------------- #
# OBS-S2-03 - future start_at is never overdue                                 #
# --------------------------------------------------------------------------- #
def test_future_start_at_not_overdue(db):
    _task(
        db,
        key="future",
        start_at=NOW + timedelta(days=1),
        last_run_at=NOW - timedelta(days=30),
    )
    assert svc.get_overdue_tasks(db, NOW) == []


# --------------------------------------------------------------------------- #
# OBS-S2-04 - grace clamp + boundary                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "unit,value,expected",
    [
        ("minutes", 5, timedelta(seconds=75)),      # 25% of 5m = 75s, inside clamp
        ("seconds", 30, timedelta(seconds=60)),     # 25% of 30s = 7.5s -> floor 60s
        ("hours", 1, timedelta(minutes=15)),        # 25% of 1h = 15m, inside clamp
        ("days", 1, timedelta(minutes=30)),         # 25% of 1d = 6h -> ceiling 30m
    ],
)
def test_grace_is_percentage_clamped_60s_to_30min(db, unit, value, expected):
    t = _task(db, interval_unit=unit, interval_value=value)
    assert svc.compute_grace(t, grace_percent=25) == expected


def test_not_overdue_exactly_at_due_plus_grace(db):
    """Boundary: == due_at + grace is NOT overdue."""
    # interval 10m -> grace 25% = 150s
    last = NOW - timedelta(minutes=10) - timedelta(seconds=150)
    _task(db, key="boundary", last_run_at=last, interval_value=10)
    assert svc.get_overdue_tasks(db, NOW, grace_percent=25) == []


def test_overdue_one_second_past_due_plus_grace(db):
    last = NOW - timedelta(minutes=10) - timedelta(seconds=151)
    _task(db, key="boundary", last_run_at=last, interval_value=10)
    overdue = svc.get_overdue_tasks(db, NOW, grace_percent=25)
    assert [o.task.key for o in overdue] == ["boundary"]
    assert overdue[0].late_by == timedelta(seconds=151)


def test_late_but_inside_grace_is_not_overdue(db):
    """The false-alarm case: genuinely late, but not late enough to matter."""
    last = NOW - timedelta(minutes=11)  # 1m past a 10m interval, grace 150s
    _task(db, key="jitter", last_run_at=last, interval_value=10)
    assert svc.get_overdue_tasks(db, NOW, grace_percent=25) == []


# --------------------------------------------------------------------------- #
# OBS-S2-05 - per-task grace override wins over global                         #
# --------------------------------------------------------------------------- #
def test_per_task_grace_percent_overrides_global(db):
    t = _task(db, interval_unit="hours", interval_value=1, metadata_={"grace_percent": 50})
    assert svc.compute_grace(t, grace_percent=25) == timedelta(minutes=30)


def test_task_without_override_uses_global(db):
    t = _task(db, interval_unit="hours", interval_value=1, metadata_={"other": "x"})
    assert svc.compute_grace(t, grace_percent=25) == timedelta(minutes=15)


def test_per_task_override_can_suppress_a_noisy_task(db):
    """grace_percent large enough that a chronically-late task stops alerting."""
    last = NOW - timedelta(minutes=20)
    _task(
        db,
        key="noisy",
        last_run_at=last,
        interval_unit="minutes",
        interval_value=10,
        metadata_={"grace_percent": 300},  # 30m, clamped to ceiling 30m
    )
    assert svc.get_overdue_tasks(db, NOW, grace_percent=25) == []


def test_invalid_per_task_grace_falls_back_to_global(db):
    t = _task(db, interval_unit="hours", interval_value=1, metadata_={"grace_percent": "abc"})
    assert svc.compute_grace(t, grace_percent=25) == timedelta(minutes=15)


# --------------------------------------------------------------------------- #
# OBS-S2-07 - disabled tasks never overdue                                     #
# --------------------------------------------------------------------------- #
def test_disabled_task_never_overdue(db):
    _task(db, key="off", enabled=False, last_run_at=NOW - timedelta(days=30))
    assert svc.get_overdue_tasks(db, NOW) == []


# --------------------------------------------------------------------------- #
# OBS-S2-09 - lateness measured from due_at, not from due_at + grace           #
# --------------------------------------------------------------------------- #
def test_late_by_measured_from_due_at(db):
    last = NOW - timedelta(minutes=33)  # interval 10m -> due 23m ago
    _task(db, key="late", last_run_at=last, interval_value=10)
    overdue = svc.get_overdue_tasks(db, NOW, grace_percent=25)
    assert overdue[0].late_by == timedelta(minutes=23)


# --------------------------------------------------------------------------- #
# OBS-S2-06 - both surfaces agree, because both call this helper               #
# --------------------------------------------------------------------------- #
def test_health_and_watchdog_report_identical_overdue_sets(db):
    """The whole point of the slice: one helper, one answer."""
    from app.api.v1.system import health as health_mod
    from app.services import system_health_alert_service as alert_svc

    # never-ran (the case the two surfaces disagreed on), plus a genuinely stuck task
    _task(db, key="never_ran", last_run_at=None, created_at=NOW - timedelta(days=1))
    _task(db, key="stuck", last_run_at=NOW - timedelta(hours=6), interval_value=10)
    _task(db, key="fine", last_run_at=NOW - timedelta(minutes=1), interval_value=10)

    shared = {o.task.key for o in svc.get_overdue_tasks(db, NOW)}
    card = health_mod._scheduled_tasks_health(db, NOW)
    _, detail = alert_svc._eval_scheduled_tasks(db, NOW)

    assert shared == {"never_ran", "stuck"}
    assert card.overdue == len(shared)
    for key in shared:
        assert key in detail
    assert "fine" not in detail
