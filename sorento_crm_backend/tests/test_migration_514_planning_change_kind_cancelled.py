"""Migration 514's data-only rename (Slice A, `documentation/plans/scm/PLAN-scm-change
-management-one-engine.md`): `projects.planning_change_rows.kind == 'closed'` becomes
`'cancelled'`, the CLOSED row-kind rename rule 5 spells out. Driven the same way
`tests/test_migration_513_planning_gate_backfill.py` drives its own migration - loaded by
path with `importlib`, run against a scratch-schema Postgres session
(`tests/_pg_fixture.blank_session`), never sqlite; every FK the model needs
(`projects.sales_orders` for `project_sales_order_id`) is seeded here directly.

Until the coder's migration lands this file does not exist at
`alembic/versions/514_planning_change_kind_cancelled.py`, so every test below fails at
`_load_migration` with a `FileNotFoundError` - the expected red, not a fixture bug.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.base import company_scope
from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import ProjectSalesOrder
from tests._pg_fixture import blank_session

MARKER = "zzt-514"

MIGRATION = (
    Path(__file__).resolve().parent
    / ".."
    / "alembic"
    / "versions"
    / "514_planning_change_kind_cancelled.py"
).resolve()


def _uid() -> str:
    return str(uuid.uuid4())


def _load_migration():
    spec = importlib.util.spec_from_file_location("m514", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_apply(db) -> None:
    module = _load_migration()
    module.apply(db.connection())


def _run_revert(db) -> None:
    module = _load_migration()
    module.revert(db.connection())


@pytest.fixture()
def world():
    from sqlalchemy import text

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


def _batch(db, company_id) -> PlanningChangeBatch:
    batch = PlanningChangeBatch(id=_uid(), company_id=company_id, order_count=1, line_count=1)
    db.add(batch)
    db.flush()
    return batch


def _row(db, company_id, batch, order, *, kind) -> PlanningChangeRow:
    row = PlanningChangeRow(
        id=_uid(), company_id=company_id, batch_id=batch.id,
        project_sales_order_id=order.id, kind=kind, facts_json={},
        suggested="keep", why=f"{MARKER} test row",
    )
    db.add(row)
    db.flush()
    return row


def _reload_kind(db, row_id) -> str:
    db.expire_all()
    return db.query(PlanningChangeRow).filter_by(id=row_id).one().kind


def test_migration_514_renames_closed_rows_to_cancelled(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    closed_row = _row(db, company_id, batch, order, kind="closed")
    untouched_row = _row(db, company_id, batch, order, kind="qty_down")

    _run_apply(db)

    assert _reload_kind(db, closed_row.id) == "cancelled"
    assert _reload_kind(db, untouched_row.id) == "qty_down"


def test_migration_514_downgrade_restores_closed(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    row = _row(db, company_id, batch, order, kind="closed")

    _run_apply(db)
    assert _reload_kind(db, row.id) == "cancelled"

    _run_revert(db)
    assert _reload_kind(db, row.id) == "closed"


def test_migration_514_is_idempotent(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    row = _row(db, company_id, batch, order, kind="closed")

    _run_apply(db)
    _run_apply(db)

    assert _reload_kind(db, row.id) == "cancelled"
