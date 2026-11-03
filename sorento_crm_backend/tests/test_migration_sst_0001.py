"""Migration `sst_0001_sample_tracking` (PS-SAMPLE-TRACKING): up, down, up.

Adds the Stage 1 date answer columns and `consignment_order_id` (FK `sales_orders`, SET NULL)
to `projects.sample_requests`. The DDL runs on the real table inside an outer transaction that
is rolled back, so nothing survives the test. Named `test_migration_*.py`: CI runs it in the
serial migration pass.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
REVISION = "sst_0001_sample_tracking"
COLUMNS = {
    "date_feasible",
    "proposed_delivery_date",
    "date_note",
    "date_answered_at",
    "date_answered_by",
    "consignment_order_id",
}


def _load():
    alembic_dir = str(VERSIONS.parent)
    if alembic_dir not in sys.path:
        sys.path.insert(0, alembic_dir)
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", VERSIONS / f"{REVISION}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def _present(conn) -> set:
    cols = {c["name"] for c in sa.inspect(conn).get_columns("sample_requests", schema="projects")}
    return COLUMNS & cols


def test_revision_id_fits_the_alembic_length_limit():
    module = _load()
    assert module.revision == REVISION
    assert len(module.revision) <= 32


def test_up_down_up():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            _run(conn, module.downgrade)
            assert _present(conn) == set()
            _run(conn, module.upgrade)
            assert _present(conn) == COLUMNS
            _run(conn, module.upgrade)  # idempotent: the shared dev DB may hold them already
            assert _present(conn) == COLUMNS
            fks = sa.inspect(conn).get_foreign_keys("sample_requests", schema="projects")
            target = {
                fk["referred_table"]
                for fk in fks
                if fk["constrained_columns"] == ["consignment_order_id"]
            }
            assert target == {"sales_orders"}
            _run(conn, module.downgrade)
            assert _present(conn) == set()
            _run(conn, module.upgrade)
            assert _present(conn) == COLUMNS
        finally:
            outer.rollback()
