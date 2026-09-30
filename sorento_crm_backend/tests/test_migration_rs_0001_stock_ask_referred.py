"""Migration `rs_0001_stock_ask_referred` (REFER-SALESMAN, AC-RS17): `stock_asks.quantity`
nullable and the branch CHECK grown by `incoming_eta` and `referred`; up, again
(re-runnable), and down.

Runs inside one outer transaction that is rolled back, so the shared test database keeps the
shape `Base.metadata.create_all` built. CI runs `tests/test_migration_*.py` serially.
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


def _quantity_nullable(conn) -> bool:
    cols = {c["name"]: c for c in sa.inspect(conn).get_columns("stock_asks")}
    return bool(cols["quantity"]["nullable"])


def _branch_check(conn) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_stock_asks_branch' AND conrelid = 'stock_asks'::regclass"
        )
    ).scalar()


def test_revision_fits_alembic_version():
    module = _load("rs_0001_stock_ask_referred")
    assert len(module.revision) <= 32
    assert module.down_revision


def test_upgrade_is_rerunnable_then_downgrade():
    module = _load("rs_0001_stock_ask_referred")
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            _run(conn, module.downgrade)
            assert _quantity_nullable(conn) is False
            assert "'incoming_eta'" not in (_branch_check(conn) or "")

            _run(conn, module.upgrade)
            _run(conn, module.upgrade)  # re-runnable
            assert _quantity_nullable(conn) is True
            check = _branch_check(conn) or ""
            for value in ("too_big", "in_stock", "incoming", "no_incoming", "incoming_eta", "referred"):
                assert f"'{value}'" in check, check

            _run(conn, module.downgrade)
            assert _quantity_nullable(conn) is False
            assert "'referred'" not in (_branch_check(conn) or "")
        finally:
            outer.rollback()
