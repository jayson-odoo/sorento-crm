"""Migration 513's backfill, tested by running it (AC-G6,
`documentation/plans/scm/PLAN-scm-planning-change-gate-held-or-inquiry.md`).

Reviewer finding S2: the migration's SQL is being moved out of `upgrade()`/`downgrade()`
into module-level `apply(connection)` / `revert(connection)` functions (the coder's own
concurrent restructure, in flight on this same branch - the pattern is `511_...` and the
data-only migration tests already in this file's family, e.g.
`tests/test_migration_323_container_status_company_backfill.py`). Driven the same way:
loaded by path with `importlib`, run against a scratch-schema Postgres session
(`tests/_pg_fixture.blank_session`), never sqlite - CI's database has no data, so asserting
against the live one proves nothing.

Every real FK the two models need (`projects.sales_orders` for `project_sales_order_id`) is
seeded here directly - no product, no core sales order, no supply decision - `held_json` /
`inquiry_rows_json` are the only facts the migration reads, and both are plain JSONB
columns on `PlanningChangeRow` with no further FK of their own.

Until the coder's restructure lands, `module.apply` does not exist and every test below
fails at the `_run_apply` call with `AttributeError: module '...' has no attribute
'apply'` - the expected red, not a fixture bug. Once it lands, expect every test green
except the S1 one (`test_an_all_failed_batch_stays_retryable`), which stays red until the
coder's predicate fix (excluding a `failed` row, not only a `pending` one, from "nothing
left to re-decide") lands too.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import company_scope
from app.models.planning_change import (
    PLANNING_CHANGE_STATE_FAILED,
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.project_so import ProjectSalesOrder
from tests._pg_fixture import blank_session

MARKER = "zzt-513"
CLOSED_BY = "513_planning_gate_backfill"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "513_planning_gate_backfill.py"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _load_migration():
    spec = importlib.util.spec_from_file_location("m513", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_apply(db) -> None:
    """Calls the module-level `apply(connection)` the coder's restructure adds.

    Deliberately NOT wrapped in a `MigrationContext`/`Operations` shim the way
    `test_migration_323`'s `_run_upgrade` wraps `upgrade()` - the whole point of the S2
    restructure is that the SQL runs off a plain connection, no alembic `op` needed to
    test it. An `AttributeError` here (module has no attribute `apply`) means the
    restructure has not landed yet - the expected red.
    """
    module = _load_migration()
    module.apply(db.connection())


@pytest.fixture()
def world():
    with blank_session() as db:
        company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        with company_scope(db, frozenset({company_id})):
            yield db, company_id


def _order(db, company_id) -> ProjectSalesOrder:
    order = ProjectSalesOrder(
        id=_uid(), company_id=company_id, provisional_ref=f"{MARKER}-{_uid()[:8]}",
    )
    db.add(order)
    db.flush()
    return order


def _batch(db, company_id, **overrides) -> PlanningChangeBatch:
    fields = {"id": _uid(), "company_id": company_id, "order_count": 1, "line_count": 1}
    fields.update(overrides)
    batch = PlanningChangeBatch(**fields)
    db.add(batch)
    db.flush()
    return batch


def _row(db, company_id, batch, order, **overrides) -> PlanningChangeRow:
    fields = {
        "id": _uid(), "company_id": company_id, "batch_id": batch.id,
        "project_sales_order_id": order.id, "kind": "delayed", "facts_json": {},
        "suggested": "keep", "why": f"{MARKER} test row",
        "applied_state": PLANNING_CHANGE_STATE_PENDING,
    }
    fields.update(overrides)
    row = PlanningChangeRow(**fields)
    db.add(row)
    db.flush()
    return row


def _reload(db, model, obj_id):
    db.expire_all()
    return db.query(model).filter_by(id=obj_id).one()


def _snapshot(db, *, batch_ids, row_ids):
    db.expire_all()
    batches = {
        b.id: (b.applied_at, b.applied_by, (b.result_json or {}).get("closed_by"))
        for b in db.query(PlanningChangeBatch).filter(PlanningChangeBatch.id.in_(batch_ids)).all()
    }
    rows = {
        r.id: (r.applied_state, r.applied_reason)
        for r in db.query(PlanningChangeRow).filter(PlanningChangeRow.id.in_(row_ids)).all()
    }
    return batches, rows


# --------------------------------------------------------------------------- #
# 1. no held, no inquiry -> superseded with a reason naming this migration
# --------------------------------------------------------------------------- #

def test_pending_row_with_no_held_and_no_inquiry_becomes_superseded(world):
    """Both shapes of "nothing to re-decide" close out the same way: SQL NULL on both
    columns, and the shape `build_batch` itself would have written for an added line -
    JSON null `held_json` next to an empty `inquiry_rows_json` array."""
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    sql_null_row = _row(db, company_id, batch, order, held_json=None, inquiry_rows_json=None)
    json_null_row = _row(
        db, company_id, batch, order, held_json=JSONB.NULL, inquiry_rows_json=[],
    )

    _run_apply(db)

    for row_id in (sql_null_row.id, json_null_row.id):
        row = _reload(db, PlanningChangeRow, row_id)
        assert row.applied_state == PLANNING_CHANGE_STATE_SUPERSEDED, row_id
        assert CLOSED_BY in (row.applied_reason or ""), row_id


# --------------------------------------------------------------------------- #
# 2. held, or an open inquiry -> left pending
# --------------------------------------------------------------------------- #

def test_pending_row_with_held_or_inquiry_stays_pending(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    held_row = _row(
        db, company_id, batch, order,
        held_json={"reserve": [{"warehouse_id": _uid(), "qty": "10"}]},
        inquiry_rows_json=None,
    )
    inquiry_row = _row(
        db, company_id, batch, order,
        held_json=None,
        inquiry_rows_json=[{"id": _uid(), "verb": "buy", "qty": "5", "state": "raised"}],
    )

    _run_apply(db)

    assert _reload(db, PlanningChangeRow, held_row.id).applied_state == PLANNING_CHANGE_STATE_PENDING
    assert _reload(db, PlanningChangeRow, inquiry_row.id).applied_state == PLANNING_CHANGE_STATE_PENDING


# --------------------------------------------------------------------------- #
# 3. a batch closed out only once every one of its rows is superseded
# --------------------------------------------------------------------------- #

def test_batch_all_superseded_is_closed_a_batch_with_one_pending_row_stays_open(world):
    db, company_id = world
    order = _order(db, company_id)

    closed_batch = _batch(db, company_id)
    _row(db, company_id, closed_batch, order, held_json=None, inquiry_rows_json=None)
    _row(db, company_id, closed_batch, order, held_json=None, inquiry_rows_json=[])

    open_batch = _batch(db, company_id)
    _row(db, company_id, open_batch, order, held_json=None, inquiry_rows_json=None)
    _row(db, company_id, open_batch, order, held_json={"reserve": []}, inquiry_rows_json=None)

    _run_apply(db)

    closed = _reload(db, PlanningChangeBatch, closed_batch.id)
    assert closed.applied_at is not None
    assert closed.applied_by is None
    assert (closed.result_json or {}).get("closed_by") == CLOSED_BY

    still_open = _reload(db, PlanningChangeBatch, open_batch.id)
    assert still_open.applied_at is None


# --------------------------------------------------------------------------- #
# 4. S1: an all-failed batch must stay retryable
# --------------------------------------------------------------------------- #

def test_an_all_failed_batch_stays_retryable(world):
    """Reviewer S1: a batch with no `pending` row left because its only surviving row is
    `failed` (never touched by this migration - `failed` is not `pending`) must NOT read
    as "nothing left to re-decide". `applied_at` must stay NULL so it is still retryable.
    Expected red until the coder's predicate fix lands: today's `NOT EXISTS ...
    applied_state = 'pending'` also matches an all-failed batch and closes it."""
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    _row(
        db, company_id, batch, order, held_json=None, inquiry_rows_json=None,
        applied_state=PLANNING_CHANGE_STATE_FAILED,
    )

    _run_apply(db)

    assert _reload(db, PlanningChangeBatch, batch.id).applied_at is None


# --------------------------------------------------------------------------- #
# 5. an already-applied batch, and its rows, are untouched
# --------------------------------------------------------------------------- #

def test_a_batch_already_applied_is_untouched(world):
    db, company_id = world
    order = _order(db, company_id)
    already_applied_at = datetime(2026, 8, 1, 9, 0, 0)
    batch = _batch(db, company_id, applied_at=already_applied_at)
    # Would otherwise qualify for supersede - the batch-scoping join (`applied_at IS
    # NULL`) is what must keep this alone, not the row's own shape.
    row = _row(db, company_id, batch, order, held_json=None, inquiry_rows_json=None)

    _run_apply(db)

    reloaded_batch = _reload(db, PlanningChangeBatch, batch.id)
    reloaded_row = _reload(db, PlanningChangeRow, row.id)
    assert reloaded_batch.applied_at == already_applied_at
    assert reloaded_row.applied_state == PLANNING_CHANGE_STATE_PENDING


# --------------------------------------------------------------------------- #
# 6. idempotent
# --------------------------------------------------------------------------- #

def test_apply_twice_changes_nothing_on_the_second_run(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    superseded_row = _row(db, company_id, batch, order, held_json=None, inquiry_rows_json=None)
    held_row = _row(
        db, company_id, batch, order, held_json={"reserve": []}, inquiry_rows_json=None,
    )
    failed_batch = _batch(db, company_id)
    failed_row = _row(
        db, company_id, failed_batch, order, held_json=None, inquiry_rows_json=None,
        applied_state=PLANNING_CHANGE_STATE_FAILED,
    )

    batch_ids = [batch.id, failed_batch.id]
    row_ids = [superseded_row.id, held_row.id, failed_row.id]

    _run_apply(db)
    first_pass = _snapshot(db, batch_ids=batch_ids, row_ids=row_ids)

    _run_apply(db)
    second_pass = _snapshot(db, batch_ids=batch_ids, row_ids=row_ids)

    assert first_pass == second_pass


# --------------------------------------------------------------------------- #
# 7. nothing is ever deleted
# --------------------------------------------------------------------------- #

def test_apply_deletes_no_row_and_no_batch(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    _row(db, company_id, batch, order, held_json=None, inquiry_rows_json=None)
    _row(db, company_id, batch, order, held_json={"reserve": []}, inquiry_rows_json=None)

    before_rows = db.query(PlanningChangeRow).count()
    before_batches = db.query(PlanningChangeBatch).count()

    _run_apply(db)

    after_rows = db.query(PlanningChangeRow).count()
    after_batches = db.query(PlanningChangeBatch).count()
    assert after_rows == before_rows
    assert after_batches == before_batches
