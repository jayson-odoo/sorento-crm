"""Migration `cpc3_lead_time_nullable` (#1288 round 6, R3): up, down, up.

The owner's ruling of 28 Sep 2026 ("don't need Lead time (days)"): a link the cost upload
creates may have no lead time, so `product_suppliers.standard_lead_time_days` drops NOT NULL.
The downgrade fills an empty lead time with 90 (the `resolve_standard_lead_time_days` fallback)
before putting NOT NULL back.

The migration's own `upgrade()` / `downgrade()` run through a real alembic `Operations` context
against a scratch `product_suppliers` on a scratch schema, reached through `search_path` (the
migration names the table unqualified): an ALTER on the shared table would lock it for every
other worker, and a rolled-back transaction is not isolation for DDL (lesson 114).
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

MIGRATION = (
    Path(__file__).resolve().parent / ".." / "alembic" / "versions" / "cpc3_lead_time_nullable.py"
).resolve()


def _load():
    spec = importlib.util.spec_from_file_location("m_cpc3", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _nullable(conn, schema: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_schema = :s "
            "AND table_name = 'product_suppliers' AND column_name = 'standard_lead_time_days'"
        ),
        {"s": schema},
    ).scalar() == "YES"


def test_revision_fits_alembic_version_and_sits_on_cpc2():
    module = _load()
    assert module.revision == "cpc3_lead_time_nullable"
    assert len(module.revision) <= 32
    assert module.down_revision == "cpc2_cost_price_tick_schedule"


def test_up_down_up_on_a_scratch_table():
    module = _load()
    scratch = f"zzs_mig_cpc3_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
            conn.exec_driver_sql(
                "CREATE TABLE product_suppliers (id int PRIMARY KEY, standard_lead_time_days int NOT NULL)"
            )
            conn.exec_driver_sql("INSERT INTO product_suppliers VALUES (1, 30)")
            assert not _nullable(conn, scratch)

            _run(conn, module.upgrade)
            assert _nullable(conn, scratch)
            conn.exec_driver_sql("INSERT INTO product_suppliers VALUES (2, NULL)")

            _run(conn, module.downgrade)
            assert not _nullable(conn, scratch)
            rows = dict(conn.exec_driver_sql("SELECT id, standard_lead_time_days FROM product_suppliers").all())
            assert rows == {1: 30, 2: 90}

            _run(conn, module.upgrade)
            assert _nullable(conn, scratch)
        finally:
            outer.rollback()
