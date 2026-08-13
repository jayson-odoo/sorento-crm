"""The committed_v migration chain must replay from history, not from today's code.

Production's first replay of the SCM chain died at migration 340: it imported the LIVE
`COMMITTED_V_SQL`, which by then carried the S13b `demand_origin` clause, referencing a
column only migration 346 adds. Dev never saw it because dev had already passed 340 with
the old body. Two invariants pin the fix:

1. REPLAY: on a schema shaped like the world at 339 (no `demand_origin` column), 340's
   `upgrade()` must succeed, and 346's must succeed after it - the exact sequence that
   failed in production.
2. DRIFT GUARD: the newest view-freezing migration's body must equal the live
   `COMMITTED_V_SQL`. When someone edits the live SQL, this goes red and the fix is a NEW
   migration freezing the new body - never editing an old migration, never importing live
   code from one.
"""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.services.scm.demand import COMMITTED_V_SQL
from tests._pg_fixture import blank_session
from tests.scm.conftest import requires_pg

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _normalize(sql: str) -> str:
    return " ".join(
        line.strip()
        for line in sql.strip().splitlines()
        if line.strip() and not line.strip().startswith("--")
    )


@requires_pg
def test_migration_bodies_are_frozen_not_imported():
    """Neither view migration may import the live SQL - that import IS the outage."""
    for name in ("340_scm_committed_reads_the_decision", "346_scm_demand_origin_split"):
        source = (_VERSIONS / f"{name}.py").read_text()
        assert "from app.services" not in source, (
            f"{name} imports live application code; freeze the SQL in the migration "
            "instead - a migration describes a point in history."
        )


@requires_pg
def test_newest_view_migration_matches_the_live_body():
    """Edit COMMITTED_V_SQL -> this goes red -> write a NEW migration with the new body."""
    m346 = _load("346_scm_demand_origin_split")
    assert _normalize(m346._AS_OF_346) == _normalize(COMMITTED_V_SQL), (
        "app.services.scm.demand.COMMITTED_V_SQL changed. Do not edit migration 346; "
        "add a new migration that freezes the new body (346's pattern), so a from-zero "
        "replay stays true to history."
    )


@requires_pg
def test_replaying_340_then_346_on_a_339_shaped_schema():
    """The exact production failure path: 340 before demand_origin exists, then 346."""
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        # blank_session built today's model schema; put it back to the world as
        # migration 339 left it: the column 346 adds must not exist yet.
        db.execute(text("ALTER TABLE sales_orders DROP COLUMN IF EXISTS demand_origin"))

        conn = db.connection()
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as op_module

        op_module._proxy = ops
        _load("340_scm_committed_reads_the_decision").upgrade()

        # 346 adds demand_origin itself, then re-emits the view with the S13b clause.
        _load("346_scm_demand_origin_split").upgrade()

        definition = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert definition and "demand_origin" in definition
