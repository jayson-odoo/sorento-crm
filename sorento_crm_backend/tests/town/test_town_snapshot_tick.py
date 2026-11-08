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


def test_the_tick_takes_the_lock_with_a_240_second_expiry(env):
    _redis().delete("town:lock")
    env.town.run_town_snapshot_tick(now=myt(DAY, 10, 0))
    ttl = _redis().ttl("town:lock")
    assert 0 < ttl <= 240


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
    _tick(env, myt(DAY, 10, 0))  # must not raise
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
