"""Migration 515's new column (Slice C, `documentation/plans/scm/PLAN-scm-change-
management-one-engine.md`): `projects.planning_change_rows.suggestion_json` (JSONB), plus
the data-only decision remap `accept`/`keep` -> `confirm`, `board` -> `null`. Driven the
same way `tests/test_migration_514_planning_change_kind_cancelled.py` drives its own
migration - loaded by path with `importlib`, run against a scratch-schema Postgres session
(`tests/_pg_fixture.blank_session`), never sqlite; every FK the model needs is seeded here
directly.

Until the coder's migration lands this file does not exist at
`alembic/versions/515_planning_change_suggestion.py`, so every test below fails at
`_load_migration` with a `FileNotFoundError` - the expected red, not a fixture bug.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import ProjectSalesOrder
from tests._pg_fixture import blank_session

MARKER = "zzt-515"

MIGRATION = (
    Path(__file__).resolve().parent
    / ".."
    / "alembic"
    / "versions"
    / "515_planning_change_suggestion.py"
).resolve()


def _uid() -> str:
    return str(uuid.uuid4())


def _load_migration():
    spec = importlib.util.spec_from_file_location("m515", MIGRATION)
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


def _row(db, company_id, batch, order, *, decision) -> PlanningChangeRow:
    row = PlanningChangeRow(
        id=_uid(), company_id=company_id, batch_id=batch.id,
        project_sales_order_id=order.id, kind="qty_down", facts_json={},
        suggested="keep", why=f"{MARKER} test row", decision=decision,
    )
    db.add(row)
    db.flush()
    return row


def test_migration_515_adds_the_suggestion_json_column(world):
    """Before `apply()`, a raw SELECT of the column 500s (`UndefinedColumn`); after, it
    reads NULL for a pre-existing row - the column exists but nothing has backfilled it."""
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    row = _row(db, company_id, batch, order, decision=None)
    db.commit()

    _run_apply(db)

    value = db.execute(
        text("select suggestion_json from projects.planning_change_rows where id = :id"),
        {"id": row.id},
    ).scalar()
    assert value is None


def test_migration_515_remaps_accept_and_keep_to_confirm(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    accept_row = _row(db, company_id, batch, order, decision="accept")
    keep_row = _row(db, company_id, batch, order, decision="keep")
    untouched_row = _row(db, company_id, batch, order, decision="confirm")
    db.commit()

    _run_apply(db)

    def _decision(row_id):
        db.expire_all()
        return db.query(PlanningChangeRow).filter_by(id=row_id).one().decision

    assert _decision(accept_row.id) == "confirm"
    assert _decision(keep_row.id) == "confirm"
    assert _decision(untouched_row.id) == "confirm"


def test_migration_515_remaps_board_to_null(world):
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    board_row = _row(db, company_id, batch, order, decision="board")
    db.commit()

    _run_apply(db)

    db.expire_all()
    assert db.query(PlanningChangeRow).filter_by(id=board_row.id).one().decision is None


def test_migration_515_downgrade_drops_the_column_and_leaves_decisions_as_they_are(world):
    """The revert is documented as data-preserving for `decision` (only the column goes) -
    the remap from `accept`/`keep`/`board` is one-way, same as 514's kind rename is NOT
    (514 is symmetric; this one is asymmetric on purpose, since `board` collapsing to
    `null` cannot be told apart from a row that was always `null`)."""
    db, company_id = world
    order = _order(db, company_id)
    batch = _batch(db, company_id)
    row = _row(db, company_id, batch, order, decision="accept")
    db.commit()

    _run_apply(db)
    db.expire_all()
    assert db.query(PlanningChangeRow).filter_by(id=row.id).one().decision == "confirm"

    _run_revert(db)

    with pytest.raises(Exception):
        db.execute(
            text("select suggestion_json from projects.planning_change_rows where id = :id"),
            {"id": row.id},
        )
        db.connection().commit()
