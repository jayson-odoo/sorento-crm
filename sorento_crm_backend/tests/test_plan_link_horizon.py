"""S2 (code review, 27 Aug 2026): the link horizon's default is the reorder PLAN RUN's
own "Plan until", not the fulfilment policy's `reorder_coverage_until`.

`PLAN-scm-oi-handshake.md` section 11. The two dates say opposite things about the same
rows. `reorder_coverage_until` is the ladder's BUY-NOW line - "a line required after this
date is proposed Buy now" (`front_planning_engine`, `scm.priority_policy`) - so the rows
beyond it are exactly the ones the engine ordered bought, and taking it as the link
horizon meant the purchase order raised for them could never be linked back to them.
`reorder_run.plan_horizon_date` is the run's own "Plan until", the date its netting stops
at, which is the honest answer to "how far out has anybody planned".

`blank_session`, so `scm.reorder_run` is EMPTY: the shared local database is a prod copy
carrying real planning runs, and "the latest completed run" is not a sentence a test may
say out loud against those.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.scm import priority

from ._pg_fixture import blank_session

#: Far enough apart that `finished_at` orders them, and stated rather than derived from
#: `now()` - every row this file writes shares one transaction, so `now()` is one value.
EARLIER = datetime(2026, 8, 1, 9, 0, 0)
LATER = datetime(2026, 8, 20, 9, 0, 0)


@pytest.fixture()
def db():
    with blank_session() as session:
        company_id = session.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        with company_scope(session, frozenset({company_id})):
            yield session


def _run(db, *, status: str, horizon, finished_at):
    """One planning run, at a status and a horizon."""
    from app.models.scm import ReorderRun

    run = ReorderRun(
        id=str(uuid.uuid4()),
        status=status,
        plan_horizon_date=horizon,
        started_at=finished_at,
        finished_at=finished_at,
    )
    db.add(run)
    db.flush()
    return run


def test_no_run_at_all_means_no_horizon(db):
    """A fresh install has never been asked how far out it plans, and a guessed date would
    refuse links nobody asked to have refused."""
    assert priority.plan_link_horizon(db) is None


def test_the_latest_completed_run_states_the_horizon(db):
    """Two completed runs, and the one that finished last is the plan in force."""
    _run(db, status="completed", horizon=date(2026, 10, 31), finished_at=EARLIER)
    _run(db, status="completed", horizon=date(2026, 12, 31), finished_at=LATER)

    assert priority.plan_link_horizon(db) == date(2026, 12, 31)


def test_a_latest_run_that_named_no_horizon_means_no_horizon(db):
    """"Plan until" is optional - a run left blank plans every open line - and the latest
    run is the plan whether or not it named a date. Falling back to an older run's date
    would link to a horizon nobody is planning to any more."""
    _run(db, status="completed", horizon=date(2026, 10, 31), finished_at=EARLIER)
    _run(db, status="completed", horizon=None, finished_at=LATER)

    assert priority.plan_link_horizon(db) is None


def test_a_run_still_going_or_failed_is_not_the_plan(db):
    """Only a COMPLETED run has a plan behind it. A run that is still going has produced
    nothing to buy to, and a failed one produced nothing at all."""
    _run(db, status="completed", horizon=date(2026, 10, 31), finished_at=EARLIER)
    _run(db, status="running", horizon=date(2027, 1, 1), finished_at=None)
    _run(db, status="failed", horizon=date(2028, 1, 1), finished_at=LATER)

    assert priority.plan_link_horizon(db) == date(2026, 10, 31)


def test_a_named_run_states_its_own_horizon(db):
    """What a purchase-order confirm asks: the PO was drafted off THIS run, so the horizon
    it links under is the one that run planned to, not whatever has run since."""
    own = _run(db, status="completed", horizon=date(2026, 10, 31), finished_at=EARLIER)
    _run(db, status="completed", horizon=date(2027, 6, 30), finished_at=LATER)

    assert priority.plan_link_horizon(db, run_id=str(own.id)) == date(2026, 10, 31)


def test_a_run_id_nobody_knows_falls_back_to_the_latest(db):
    """One ladder in one place: a caller that cannot name a run gets the same answer as a
    caller that names none."""
    _run(db, status="completed", horizon=date(2026, 12, 31), finished_at=LATER)

    assert priority.plan_link_horizon(db, run_id=str(uuid.uuid4())) == date(2026, 12, 31)


def test_the_policys_coverage_date_is_not_the_link_horizon(db):
    """`reorder_coverage_until` is the ladder's own setting and stays untouched: it says a
    line needed after it is BOUGHT NOW, which is the opposite of "do not link past it"."""
    from app.models.scm import PriorityPolicy

    db.add(
        PriorityPolicy(
            id=str(uuid.uuid4()),
            name="ZZT link horizon",
            is_active=True,
            reorder_coverage_until=date(2026, 10, 31),
        )
    )
    db.flush()

    assert priority.fulfilment_settings(priority.active_policy(db))[
        "reorder_coverage_until"
    ] == date(2026, 10, 31)
    assert priority.plan_link_horizon(db) is None
