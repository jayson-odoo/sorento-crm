"""Scheduled task handlers must run system-scoped, or they silently scan nothing.

Every owned business table carries ``CompanyScopedMixin``, and ``do_orm_execute``
fail-closes: a session whose scope was never resolved reads as ``UNSET``, which
compiles to ``false()`` and returns zero rows.

The scheduler heartbeat opens a bare ``SessionLocal()`` and hands it straight to
``run_due_tasks``. Nothing sets a scope, so ``promotion_active_window`` ran hourly,
reported ``success`` in 5ms, and scanned 0 of 191 promotions -- which is why
promotions with a past ``end_date`` were still ``is_active = true``. The RQ workers
already do this correctly (``import_tasks``/``export_tasks`` call
``set_company_scope(db, None)``); the APScheduler path never did.

Scoping in ``run_due_tasks`` fixes every handler at once, and covers any caller,
not just the heartbeat.

Everything runs inside ``blank_session()`` -- a scratch schema whose writes are
discarded -- so the shared dev database is never touched.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.base import UNSET, get_company_scope, set_company_scope
from app.models.marketing import Promotion
from app.models.scheduled_task import ScheduledTask
from app.services.company_scope import register_company_scope_listeners
from app.services.scheduled_task_service import (
    TASK_HANDLERS,
    register_handler,
    run_due_tasks,
)

from ._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _scope_listeners():
    """The filter lives in an ORM event that app.main registers at import time.

    Without it the scope is never applied and this test proves nothing, so register
    it explicitly. It is idempotent.
    """
    register_company_scope_listeners()


def _as_the_scheduler_sees_it(db) -> None:
    """Force the production condition.

    ``tests/conftest.py`` defaults every test session to the Sorento scope
    (``session.info.setdefault("company_scope", ...)``) so legacy tests don't fail
    closed. That masks exactly the bug under test, so put the session back the way a
    bare ``SessionLocal()`` in the scheduler heartbeat actually arrives: UNSET.
    """
    set_company_scope(db, UNSET)


def _due_task(db, key: str) -> ScheduledTask:
    """An enabled task that has never run, so ``_is_task_due`` fires immediately."""
    task = ScheduledTask(
        key=key,
        name=f"probe {key}",
        enabled=True,
        interval_unit="hours",
        interval_value=1,
        timezone="UTC",
    )
    db.add(task)
    db.flush()
    return task


def test_handler_receives_a_system_scoped_session():
    """The scope must be resolved to None (all companies), never left UNSET."""
    key = f"zzt_probe_{uuid.uuid4().hex[:8]}"
    seen: dict = {}

    def probe(db, task):
        seen["scope"] = get_company_scope(db)
        return {"ok": True}

    register_handler(key, probe)
    try:
        with blank_session() as db:
            _due_task(db, key)
            _as_the_scheduler_sees_it(db)
            run_due_tasks(db)

        assert "scope" in seen, "handler never ran"
        assert seen["scope"] is not UNSET, (
            "handler got an UNSET scope - every company-scoped query it makes returns zero rows"
        )
        assert seen["scope"] is None, f"expected system scope (None), got {seen['scope']!r}"
    finally:
        TASK_HANDLERS.pop(key, None)


def test_promotion_active_window_actually_scans_promotions():
    """The symptom: scanned=0 forever, so nothing expires.

    Seeds a promotion whose window closed yesterday and is still flagged active,
    then runs the real handler the way the scheduler does.
    """
    from app.scheduler.task_scheduler import register_task_handlers

    register_task_handlers()

    with blank_session() as db:
        today = date.today()
        expired = Promotion(
            description=unique_code("EXPIRED"),
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
            is_active=True,
        )
        db.add(expired)
        db.flush()
        expired_id = expired.id

        _due_task(db, "promotion_active_window")
        _as_the_scheduler_sees_it(db)
        run_due_tasks(db)

        # Read back system-scoped: the assertion query would otherwise inherit the
        # UNSET scope set above and find nothing regardless of what the handler did.
        set_company_scope(db, None)
        row = db.query(Promotion).filter(Promotion.id == expired_id).one()
        assert row.is_active is False, (
            "a promotion past its end_date is still active - the handler scanned nothing"
        )


def test_a_live_promotion_is_left_active():
    """Guard the other direction: the sweep must not deactivate a current promotion."""
    from app.scheduler.task_scheduler import register_task_handlers

    register_task_handlers()

    with blank_session() as db:
        today = date.today()
        live = Promotion(
            description=unique_code("LIVE"),
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=30),
            is_active=True,
        )
        db.add(live)
        db.flush()
        live_id = live.id

        _due_task(db, "promotion_active_window")
        _as_the_scheduler_sees_it(db)
        run_due_tasks(db)

        set_company_scope(db, None)
        assert db.query(Promotion).filter(Promotion.id == live_id).one().is_active is True
