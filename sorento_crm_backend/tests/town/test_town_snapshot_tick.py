"""SORENTO-TOWN Phase 0: `run_town_snapshot_tick(now=...)` (AC-8, AC-9).

Assumptions the contract leaves open (listed in the lane report):
- the tick opens its database session through `scheduler_session` (or `SessionLocal`), both of
  which this suite redirects to the test's blank-schema session;
- Redis is `app.services.queue_service.redis_conn`;
- `build_snapshot` is looked up on the snapshot module at call time, so monkeypatching
  `app.services.town.snapshot.build_snapshot` replaces it for the tick.
"""
from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import cust, doc
from tests.town._town_seed import DAY, D, fake_full, myt

INACTIVE_ID = "00000000-0000-0000-0000-0000000000a3"


class _KeepOpen:
    """The test's session, whose close() is a no-op so the tick cannot end the test's transaction."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass


@pytest.fixture
def env(monkeypatch):
    from app.scheduler import task_scheduler
    from app.services.town import snapshot as town  # red here until the service exists

    with blank_session() as db:
        set_company_scope(db, None)
        seed_mocha(db)
        dead = Company(id=INACTIVE_ID, name="ZZT Dead", code=unique_code("DEAD")[:20], is_active=False)
        db.add(dead)
        db.flush()
        keep = _KeepOpen(db)

        @contextmanager
        def fake_scheduler_session(name="scheduler"):
            yield keep

        monkeypatch.setattr(task_scheduler, "scheduler_session", fake_scheduler_session)
        monkeypatch.setattr(town, "scheduler_session", fake_scheduler_session, raising=False)
        monkeypatch.setattr(town, "SessionLocal", lambda: keep, raising=False)

        calls: list[str] = []

        def fake_build(session, company_id, day, *, now):
            calls.append(company_id)
            snap = fake_full(day, company_id)
            snap["today"]["invoice_count"] = len(calls)  # lets a later tick be told from an earlier one
            return snap

        monkeypatch.setattr(town, "build_snapshot", fake_build)
        yield type("Env", (), {"db": db, "calls": calls, "town": town, "patch": monkeypatch})


def _redis():
    from app.services.queue_service import redis_conn

    return redis_conn


def _tick(env, now):
    _redis().delete("town:lock")  # the lock outlives a tick (EX 240); each call here is a later tick
    env.town.run_town_snapshot_tick(now=now)


def _keys_for(company_id):
    return list(_redis().scan_iter(match=f"town:{company_id}:*"))


# --------------------------------------------------------------------------- AC-8


def test_outside_the_window_the_tick_does_nothing(env):
    for now in (myt(DAY, 6, 59), myt(DAY, 22, 6), myt(DAY, 23, 30), myt(DAY, 3, 0)):
        _tick(env, now)
    assert env.calls == []
    assert _keys_for(DEFAULT_COMPANY_ID) == [] and _keys_for(MOCHA_ID) == []
    assert not _redis().exists("town:lock")  # it did not even take the lock


def test_inside_the_window_edges_run(env):
    for now in (myt(DAY, 7, 0), myt(DAY, 22, 4)):
        _tick(env, now)
    assert len(env.calls) >= 2  # each edge builds at least one company
    assert set(env.calls) <= {DEFAULT_COMPANY_ID, MOCHA_ID}


def test_a_tick_builds_and_stores_every_active_company_and_skips_inactive(env):
    _tick(env, myt(DAY, 10, 0))
    assert sorted(env.calls) == sorted([DEFAULT_COMPANY_ID, MOCHA_ID])
    for company in (DEFAULT_COMPANY_ID, MOCHA_ID):
        keys = {k.decode() for k in _keys_for(company)}
        base = f"town:{company}:{DAY.isoformat()}"
        assert {f"{base}:full", f"{base}:redacted", f"{base}:version"} <= keys
    assert _keys_for(INACTIVE_ID) == []


def test_the_lock_has_a_240_second_expiry_during_the_build_and_is_gone_after(env):
    from app.services.town import snapshot as town

    during: list[int] = []

    def probe(session, company_id, day, *, now):
        during.append(_redis().ttl("town:lock"))
        return fake_full(day, company_id)

    env.patch.setattr(town, "build_snapshot", probe)
    _redis().delete("town:lock")
    env.town.run_town_snapshot_tick(now=myt(DAY, 10, 0))
    assert during and all(0 < ttl <= 240 for ttl in during)
    assert not _redis().exists("town:lock")  # released, so the next 3 minute tick runs


def test_a_held_lock_means_no_build(env):
    _redis().set("town:lock", "someone-else", nx=True, ex=240)
    env.town.run_town_snapshot_tick(now=myt(DAY, 10, 0))
    assert env.calls == []
    assert _keys_for(DEFAULT_COMPANY_ID) == [] and _keys_for(MOCHA_ID) == []
    assert _redis().get("town:lock") == b"someone-else"  # not stolen


def test_one_company_failing_does_not_stop_the_next(env):
    from app.services.town import snapshot as town

    attempted: list[str] = []

    def flaky(session, company_id, day, *, now):
        attempted.append(company_id)
        if company_id == DEFAULT_COMPANY_ID:
            raise RuntimeError("ZZT boom")
        return fake_full(day, company_id)

    env.patch.setattr(town, "build_snapshot", flaky)
    # SCHEDULED-TASKS-GRID: every company is still attempted, THEN the tick raises so the
    # scheduled task records the failure as its last error (it used to be a log line only).
    with pytest.raises(town.TownSnapshotFailed) as raised:
        _tick(env, myt(DAY, 10, 0))
    assert "1 of 2 companies" in str(raised.value)
    assert "ZZT boom" in str(raised.value)
    assert sorted(attempted) == sorted([DEFAULT_COMPANY_ID, MOCHA_ID])
    assert _keys_for(MOCHA_ID) != []
    assert _keys_for(DEFAULT_COMPANY_ID) == []


def test_a_build_inside_the_tick_runs_with_a_five_second_statement_timeout(env):
    from app.services.town import snapshot as town

    seen: list[str] = []

    def probe(session, company_id, day, *, now):
        seen.append(session.execute(sa.text("show statement_timeout")).scalar_one())
        return fake_full(day, company_id)

    env.patch.setattr(town, "build_snapshot", probe)
    _tick(env, myt(DAY, 10, 0))
    assert seen and all(value in ("5s", "5000ms") for value in seen), seen


# --------------------------------------------------------------------------- AC-9


def _town_days(db, company_id):
    from app.models.town import TownDay

    return db.query(TownDay).filter(TownDay.company_id == company_id, TownDay.day == DAY).all()


def test_ac9_a_daytime_tick_writes_no_town_day(env):
    _tick(env, myt(DAY, 10, 0))
    _tick(env, myt(DAY, 21, 59))
    assert _town_days(env.db, DEFAULT_COMPANY_ID) == []
    assert env.db.execute(sa.text("select count(*) from town_days")).scalar_one() == 0


def test_ac9_first_tick_at_or_after_22_freezes_the_day_with_snapshot_and_events(env):
    shop = cust(env.db, name="ZZT Frozen Shop")
    other = cust(env.db, name="ZZT Not A Shop")
    inv = doc(env.db, "invoice", "100.00", DAY, customer=shop)
    cn = doc(env.db, "credit_note", "20.00", DAY, customer=other)
    # fake_full's shops are random keys; make `shop` one of them so shop_key resolution is testable
    from app.services.town import snapshot as town

    def build(session, company_id, day, *, now):
        snap = fake_full(day, company_id)
        snap["shops"][0]["key"] = shop.id
        return snap

    env.patch.setattr(town, "build_snapshot", build)
    _tick(env, myt(DAY, 22, 1))
    rows = _town_days(env.db, DEFAULT_COMPANY_ID)
    assert len(rows) == 1
    row = rows[0]
    assert row.snapshot["schema"] == 1 and row.snapshot["company_id"] == DEFAULT_COMPANY_ID
    assert row.snapshot["shops"][0]["key"] == shop.id
    events = row.events
    assert len(events) == 2  # the day's posted documents only
    for event in events:
        assert set(event) == {"at", "shop_key", "kind", "amount"}
        assert re.fullmatch(r"\d\d:\d\d", event["at"])
        assert re.fullmatch(r"-?\d+\.\d\d", event["amount"])
    by_kind = {e["kind"]: e for e in events}
    assert set(by_kind) == {"invoice", "credit_note"}
    assert by_kind["invoice"]["shop_key"] == shop.id
    assert by_kind["credit_note"]["shop_key"] is None  # not a shop
    assert D(by_kind["invoice"]["amount"]).copy_abs() == D("100.00")
    assert D(by_kind["credit_note"]["amount"]).copy_abs() == D("20.00")


def test_ac9_events_exclude_cancelled_and_other_days(env):
    c = cust(env.db)
    doc(env.db, "invoice", "10.00", DAY, customer=c)
    doc(env.db, "invoice", "20.00", DAY, customer=c, status="cancelled")
    doc(env.db, "invoice", "30.00", DAY - timedelta(days=1), customer=c)
    _tick(env, myt(DAY, 22, 0))
    (row,) = _town_days(env.db, DEFAULT_COMPANY_ID)
    assert [D(e["amount"]).copy_abs() for e in row.events] == [D("10.00")]


def test_ac9_a_second_22_tick_updates_the_row_rather_than_duplicating(env):
    _tick(env, myt(DAY, 22, 0))
    (first,) = _town_days(env.db, DEFAULT_COMPANY_ID)
    first_count = first.snapshot["today"]["invoice_count"]
    row_id = first.id
    _tick(env, myt(DAY, 22, 3))
    env.db.expire_all()
    rows = _town_days(env.db, DEFAULT_COMPANY_ID)
    assert len(rows) == 1 and rows[0].id == row_id
    assert rows[0].snapshot["today"]["invoice_count"] != first_count  # carries the later build
    assert len(_town_days(env.db, MOCHA_ID)) == 1  # one row per company


def test_ac9_event_time_is_the_created_at_instant_in_malaysia_time(env):
    """`created_at` is naive UTC: 02:15 UTC is 10:15 in Malaysia."""
    d = doc(env.db, "invoice", "10.00", DAY, customer=cust(env.db))
    d.created_at = datetime(2026, 11, 3, 2, 15)
    env.db.flush()
    _tick(env, myt(DAY, 22, 0))
    (row,) = _town_days(env.db, DEFAULT_COMPANY_ID)
    assert [e["at"] for e in row.events] == ["10:15"]


# --------------------------------------------------------------------------- SCHEDULED-TASKS-GRID
# The Town job runs as a `scheduled_tasks` row like every other cron job, so it shows on
# System Management > Scheduled Tasks with its last run, last error, next run and Run now.


def test_the_tick_returns_a_summary_of_what_it_built(env):
    _redis().delete("town:lock")
    summary = env.town.run_town_snapshot_tick(now=myt(DAY, 10, 0))
    assert summary == {"companies": 2, "built": 2, "failed": 0}


def test_outside_the_window_the_summary_says_so(env):
    _redis().delete("town:lock")
    summary = env.town.run_town_snapshot_tick(now=myt(DAY, 23, 30))
    assert summary == {"skipped": "outside 07:00-22:05 Malaysia time"}


def test_a_held_lock_is_reported_in_the_summary(env):
    _redis().set("town:lock", "someone-else", nx=True, ex=240)
    summary = env.town.run_town_snapshot_tick(now=myt(DAY, 10, 0))
    assert summary == {"skipped": "an earlier town run is still going"}


def test_the_failure_names_the_company_not_its_id(env):
    from app.models.company import Company

    def flaky(session, company_id, day, *, now):
        if company_id == MOCHA_ID:
            raise RuntimeError("ZZT boom")
        return fake_full(day, company_id)

    env.patch.setattr(env.town, "build_snapshot", flaky)
    with pytest.raises(env.town.TownSnapshotFailed) as raised:
        _tick(env, myt(DAY, 10, 0))
    mocha_name = env.db.get(Company, MOCHA_ID).name
    assert f"{mocha_name}: ZZT boom" in str(raised.value)
    assert MOCHA_ID not in str(raised.value)


def test_town_snapshot_is_a_registered_scheduled_task_handler():
    from app.scheduler.task_scheduler import register_task_handlers
    from app.services.scheduled_task_service import TASK_HANDLERS

    register_task_handlers()
    assert "town_snapshot" in TASK_HANDLERS


def test_town_snapshot_is_no_longer_a_bare_apscheduler_job():
    """One mechanism: a second APScheduler job would run the build twice every 3 minutes."""
    import inspect

    from app.scheduler import task_scheduler

    source = inspect.getsource(task_scheduler.start_scheduler)
    assert "_town_snapshot_tick" not in source
    assert 'id="town_snapshot"' not in source


def test_a_failed_company_surfaces_as_the_scheduled_tasks_last_error(env):
    """Through the heartbeat itself: the row reads failed, with the company and the error."""
    from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun
    from app.scheduler.task_scheduler import register_task_handlers
    from app.services.scheduled_task_service import run_due_tasks

    register_task_handlers()
    # The heartbeat calls the tick with the real clock; open the window all day for the test.
    env.patch.setattr(env.town, "OPEN_MINUTE", 0)
    env.patch.setattr(env.town, "CLOSE_MINUTE", 24 * 60)
    env.patch.setattr(env.town, "NIGHT_MINUTE", 24 * 60 + 1)

    def flaky(session, company_id, day, *, now):
        if company_id == DEFAULT_COMPANY_ID:
            raise RuntimeError("ZZT boom")
        return fake_full(day, company_id)

    env.patch.setattr(env.town, "build_snapshot", flaky)
    db = env.db
    db.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = 'town_snapshot'"))
    task = ScheduledTask(
        key="town_snapshot", name="Sorento town snapshot", enabled=True,
        interval_unit="minutes", interval_value=3, timezone="UTC",
        next_run_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(task)
    db.flush()
    _redis().delete("town:lock")
    run_due_tasks(db)
    db.expire_all()
    row = db.get(ScheduledTask, task.id)
    assert row.last_status == "failed"
    assert "1 of 2 companies" in row.last_error and "ZZT boom" in row.last_error
    assert row.next_run_at is not None and row.last_run_at is not None
    (run,) = db.query(ScheduledTaskRun).filter(ScheduledTaskRun.task_id == task.id).all()
    assert run.status == "failed" and "ZZT boom" in run.error


def test_the_migration_seeds_the_town_snapshot_row():
    """Runs the seed migration's own upgrade/downgrade against a blank schema (bootstrap_env
    builds CI's DB from the models, so a migration's seed rows are never there to read)."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "town_0002_scheduled_task.py"
    spec = importlib.util.spec_from_file_location("zzt_migration_town_0002", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32

    def run(db, direction):
        context = MigrationContext.configure(connection=db.connection())
        with Operations.context(context):
            getattr(module, direction)()

    def read(db):
        return db.execute(sa.text(
            "SELECT name, interval_unit, interval_value, enabled, next_run_at "
            "FROM scheduled_tasks WHERE key = 'town_snapshot'"
        )).mappings().all()

    with blank_session() as db:
        db.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = 'town_snapshot'"))
        run(db, "upgrade")
        run(db, "upgrade")  # idempotent: a redeploy must not trip the unique key
        (row,) = read(db)
        assert row["name"] == "Sorento town snapshot"
        assert (row["interval_unit"], row["interval_value"], row["enabled"]) == ("minutes", 3, True)
        run(db, "downgrade")
        assert read(db) == []
