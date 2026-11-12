"""SCHEDULED-TASKS-GRID, owner ruling Q3 (b), 9 Nov 2026: a task with
`metadata.active_window` (Town: 07:00-22:05 Malaysia time) is not due outside it, writes no run
row and leaves Last run alone there, and is not reported overdue while its window is shut.
Its next run and due time move to the window's next opening.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.scheduled_task import ScheduledTask
from app.services import scheduled_task_service as sts
from tests._pg_fixture import blank_session, unique_code

TOWN_WINDOW = {"active_window": {"start": "07:00", "end": "22:05", "timezone": "Asia/Kuala_Lumpur"}}


def utc_of_myt(y, m, d, hh, mm=0):
    """Naive UTC (the scheduler's own clock) for a Malaysia wall time."""
    return datetime(y, m, d, hh, mm) - timedelta(hours=8)


def town(last_run_at=None, metadata=TOWN_WINDOW):
    return ScheduledTask(
        key="town_snapshot", name="Sorento town snapshot", enabled=True,
        interval_unit="minutes", interval_value=3, timezone="UTC",
        last_run_at=last_run_at, metadata_=metadata,
        created_at=utc_of_myt(2026, 11, 9, 6, 0),
    )


def test_inside_the_window_the_task_is_due_on_its_interval():
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 10, 0))
    assert sts._is_task_due(task, utc_of_myt(2026, 11, 9, 10, 3)) is True
    assert sts._is_task_due(task, utc_of_myt(2026, 11, 9, 10, 2)) is False


def test_the_window_edges_are_inclusive():
    task = town(last_run_at=utc_of_myt(2026, 11, 8, 22, 0))
    assert sts._is_task_due(task, utc_of_myt(2026, 11, 9, 7, 0)) is True
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 1))
    assert sts._is_task_due(task, utc_of_myt(2026, 11, 9, 22, 5)) is True


def test_outside_the_window_the_task_is_never_due():
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4))
    for hh, mm in ((22, 6), (23, 30), (3, 0), (6, 59)):
        day = 9 if hh >= 22 else 10
        assert sts._is_task_due(task, utc_of_myt(2026, 11, day, hh, mm)) is False


def test_the_next_run_after_the_last_tick_of_the_day_is_the_next_opening():
    task = town()
    assert sts.next_run_for(task, utc_of_myt(2026, 11, 9, 22, 4)) == utc_of_myt(2026, 11, 10, 7, 0)
    # Inside the window: the plain interval.
    assert sts.next_run_for(task, utc_of_myt(2026, 11, 9, 10, 0)) == utc_of_myt(2026, 11, 9, 10, 3)
    # Before the window opens (a Run now at 05:00): today's opening.
    assert sts.next_run_for(task, utc_of_myt(2026, 11, 9, 5, 0)) == utc_of_myt(2026, 11, 9, 7, 0)


def test_overnight_the_task_is_not_overdue():
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4))
    assert sts.compute_due_at(task, utc_of_myt(2026, 11, 10, 3, 0)) == utc_of_myt(2026, 11, 10, 7, 0)
    assert task.next_run_at is None  # (display column untouched by the read)


def test_a_run_owed_seconds_before_close_is_not_overdue_overnight():
    """Review B1: owed at 22:04:55 (inside the window), but the 10s heartbeat only gets there
    after 22:05, so it never runs; it must not read overdue all night."""
    from datetime import datetime as dt

    task = town(last_run_at=dt(2026, 11, 9, 22, 1, 55) - timedelta(hours=8))
    now = utc_of_myt(2026, 11, 10, 3, 0)
    assert sts._is_task_due(task, dt(2026, 11, 9, 22, 5, 2) - timedelta(hours=8)) is False
    due = sts.compute_due_at(task, now)
    assert due == utc_of_myt(2026, 11, 10, 7, 0)
    assert now <= due + sts.compute_grace(task, 25)


def test_just_after_opening_the_overnight_gap_is_not_lateness():
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4))
    assert sts.compute_due_at(task, utc_of_myt(2026, 11, 10, 7, 0) + timedelta(seconds=30)) == utc_of_myt(
        2026, 11, 10, 7, 0
    )


def test_get_overdue_tasks_skips_a_shut_window(monkeypatch):
    """The watchdog's own entry point, with the B1 timing."""
    from datetime import datetime as dt

    task = town(last_run_at=dt(2026, 11, 9, 22, 1, 55) - timedelta(hours=8))

    class _Q:
        def filter(self, *a):
            return self

        def all(self):
            return [task]

    class _Db:
        def query(self, *a):
            return _Q()

    assert sts.get_overdue_tasks(_Db(), now=utc_of_myt(2026, 11, 10, 3, 0), grace_percent=25) == []
    late = sts.get_overdue_tasks(_Db(), now=utc_of_myt(2026, 11, 10, 7, 5), grace_percent=25)
    assert [o.task for o in late] == [task]  # once open, a missed opening run is late again


def test_editing_the_task_shows_the_next_opening_when_it_falls_overnight(monkeypatch):
    """Review N1: `update_task` recomputes Next run through the window too."""
    from app.models.base import set_company_scope

    with blank_session() as db:
        set_company_scope(db, None)
        task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4))
        task.key = unique_code("zzt_window_edit").lower()[:100]
        db.add(task)
        db.commit()
        updated = sts.update_task(db, task.id, interval_value=3)
        assert updated.next_run_at == utc_of_myt(2026, 11, 10, 7, 0)


def test_a_task_without_a_window_is_unchanged():
    task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4), metadata=None)
    assert sts._is_task_due(task, utc_of_myt(2026, 11, 10, 3, 0)) is True
    assert sts.compute_due_at(task, utc_of_myt(2026, 11, 10, 3, 0)) == utc_of_myt(2026, 11, 9, 22, 7)


def test_a_malformed_window_is_ignored_not_fatal():
    for bad in ({"start": "7am", "end": "22:05"}, {"start": "22:00", "end": "07:00"}, {"end": "22:05"},
                {"start": "07:00", "end": "22:05", "timezone": "Mars/Base"}):
        task = town(last_run_at=utc_of_myt(2026, 11, 9, 22, 4), metadata={"active_window": bad})
        assert sts._is_task_due(task, utc_of_myt(2026, 11, 10, 3, 0)) is True


def _window_excluding_now():
    """A one-minute window that is certainly not now, in UTC."""
    now = datetime.utcnow()
    start = "12:00" if now.hour < 11 or now.hour > 13 else "00:00"
    end = "12:01" if start == "12:00" else "00:01"
    return {"active_window": {"start": start, "end": end, "timezone": "UTC"}}


def test_the_heartbeat_writes_nothing_for_a_task_outside_its_window(monkeypatch):
    from app.models.base import set_company_scope
    from app.models.scheduled_task import ScheduledTaskRun

    key = unique_code("zzt_window_task").lower()[:100]
    calls: list[str] = []
    monkeypatch.setitem(sts.TASK_HANDLERS, key, lambda db, task: calls.append("ran") or {})
    with blank_session() as db:
        set_company_scope(db, None)
        last = datetime.utcnow() - timedelta(hours=2)
        task = ScheduledTask(
            key=key, name="ZZT window task", enabled=True, interval_unit="minutes",
            interval_value=3, timezone="UTC", last_run_at=last, last_status="success",
            metadata_=_window_excluding_now(),
        )
        db.add(task)
        db.commit()
        sts.run_due_tasks(db)
        db.expire_all()
        row = db.get(ScheduledTask, task.id)
        assert calls == []
        assert row.last_run_at == last and row.last_status == "success"
        assert db.query(ScheduledTaskRun).filter(ScheduledTaskRun.task_id == task.id).count() == 0
        overdue_ids = {o.task.id for o in sts.get_overdue_tasks(db)}
        assert task.id not in overdue_ids
