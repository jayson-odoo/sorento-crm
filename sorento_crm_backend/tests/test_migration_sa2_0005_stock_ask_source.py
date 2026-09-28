"""Migration `sa2_0005_stock_ask_source` (chatbot stock ask v2 console fix round, PR #1333):
`stock_asks.source`, up, again (re-runnable), and down.

Runs inside one outer transaction that is rolled back, so the shared test database keeps the
column `Base.metadata.create_all` built. CI runs `tests/test_migration_*.py` serially.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"m_{name}", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _columns(conn) -> dict:
    return {c["name"]: c for c in sa.inspect(conn).get_columns("stock_asks")}


def _constraint(conn):
    return conn.execute(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_stock_asks_source' AND conrelid = 'stock_asks'::regclass"
        )
    ).scalar()


def test_revision_fits_alembic_version_and_sits_on_sa2_0004():
    module = _load("sa2_0005_stock_ask_source")
    assert len(module.revision) <= 32
    assert module.down_revision == "sa2_0004_stock_asks"


def test_upgrade_is_rerunnable_then_downgrade():
    module = _load("sa2_0005_stock_ask_source")
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            _run(conn, module.downgrade)
            assert "source" not in _columns(conn)

            _run(conn, module.upgrade)
            _run(conn, module.upgrade)  # re-runnable
            col = _columns(conn)["source"]
            assert col["nullable"] is False
            assert "live" in str(col["default"])

            assert _constraint(conn) is not None
            assert "'live'" in _constraint(conn) and "'console'" in _constraint(conn)

            _run(conn, module.downgrade)
            assert "source" not in _columns(conn)
            assert _constraint(conn) is None
        finally:
            outer.rollback()
