"""SCM M0 CP1 — data-model migration tests (Postgres-backed).

Verifies AC-M0.1 (migration up/down reverses cleanly, in isolation from the
sibling 272 revision), AC-M0.2 (cross-schema FK integrity), AC-M0.3
(source_system/source_ref on every new table). SQLite can't model schemas or
cross-schema FKs, so these run only against a live Postgres DATABASE_URL.
"""
from __future__ import annotations

import os
import re
import uuid

import pytest
from sqlalchemy import create_engine, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _pg_url() -> str | None:
    # DATABASE_URL env wins (CI/container); .env is a local fallback and is NOT
    # shipped in the CI image, so its absence must skip these tests, not crash.
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if not os.path.exists(env):
            return None
        with open(env) as fh:
            for line in fh:
                if line.startswith("DATABASE_URL"):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not raw:
        return None
    return re.sub(r"^postgresql\+\w+", "postgresql", raw)


URL = _pg_url()
pytestmark = pytest.mark.skipif(
    not URL or not URL.startswith("postgresql"),
    reason="CP1 schema tests require a live Postgres DATABASE_URL",
)

SCM_TABLES = {
    "reorder_policy", "item_classification", "abc_xyz_policy", "supplier_scoring_policy",
    "supplier_performance", "purchasing_budget", "reorder_run", "reorder_recommendation",
    "recommendation_override", "override_reason", "reason_action_map", "cash_ranking_policy",
    "demand_nature_map", "demand_stat", "market_research_topic", "market_signal",
    "scm_analytics_run", "market_research_run",
}
PUBLIC_NEW = {"sales_orders", "sales_order_lines", "purchase_orders", "purchase_order_lines"}


@pytest.fixture()
def conn():
    eng = create_engine(URL)
    with eng.connect() as c:
        yield c
    eng.dispose()


def test_scm_schema_and_tables_present(conn):
    rows = conn.execute(text(
        "select table_name from information_schema.tables where table_schema='scm'"
    )).scalars().all()
    assert SCM_TABLES.issubset(set(rows)), f"missing scm tables: {SCM_TABLES - set(rows)}"
    pub = conn.execute(text(
        "select table_name from information_schema.tables "
        "where table_schema='public' and table_name = any(:names)"
    ), {"names": list(PUBLIC_NEW)}).scalars().all()
    assert PUBLIC_NEW.issubset(set(pub))


def test_source_cols_on_every_new_table(conn):
    """AC-M0.3 — every new SCM table carries source_system + source_ref."""
    missing = []
    for schema, tables in (("scm", SCM_TABLES), ("public", PUBLIC_NEW)):
        for t in tables:
            cols = conn.execute(text(
                "select column_name from information_schema.columns "
                "where table_schema=:s and table_name=:t"
            ), {"s": schema, "t": t}).scalars().all()
            for needed in ("source_system", "source_ref"):
                if needed not in cols:
                    missing.append(f"{schema}.{t}.{needed}")
    assert not missing, f"tables missing source cols: {missing}"


def test_existing_tables_extended(conn):
    def cols(t):
        return set(conn.execute(text(
            "select column_name from information_schema.columns "
            "where table_schema='public' and table_name=:t"
        ), {"t": t}).scalars().all())

    assert {"moq", "order_multiple", "unit_cost", "currency", "is_primary_supplier",
            "lead_time_variability_days"} <= cols("product_suppliers")
    assert "current_performance_score" in cols("suppliers")
    assert {"po_line_id", "qty_accepted", "qty_rejected"} <= cols("picking_lines")
    assert "demand_nature" in cols("market_segments")
    assert "market_segment_code" in cols("customers")


def test_cross_schema_fk_integrity(conn):
    """AC-M0.2 — a scm row with a bad public FK is rejected; a valid one is accepted."""
    from sqlalchemy.exc import IntegrityError

    # bad product_id -> reject (savepoint rolls back the aborted insert)
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(text(
            "insert into scm.item_classification (id, product_id, source_system) "
            "values (:id, :pid, 'test')"
        ), {"id": str(uuid.uuid4()), "pid": str(uuid.uuid4())})
    sp.rollback()

    # valid product_id -> accept
    pid = conn.execute(text("select id from products limit 1")).scalar()
    assert pid is not None, "need at least one product to test the valid FK path"
    sp = conn.begin_nested()
    conn.execute(text(
        "insert into scm.item_classification (id, product_id, source_system) "
        "values (:id, :pid, 'test')"
    ), {"id": str(uuid.uuid4()), "pid": pid})
    sp.rollback()


def test_migration_downgrade_upgrade_isolated(conn):
    """AC-M0.1 — 273 reverses cleanly, tested in a rolled-back txn so the sibling
    272 revision and the live DB state are never disturbed."""
    import importlib.util

    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "alembic", "versions", "273_scm_module_schema.py")
    spec = importlib.util.spec_from_file_location("mig273", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    sp = conn.begin_nested()  # savepoint — everything below is rolled back, DB untouched
    try:
        # CP2 (274) builds views on top of 273's columns (e.g. scm.consumption_v uses
        # customers.market_segment_code). In the real chain 274 downgrades first; here we
        # isolate just 273, so drop those dependent views inside the savepoint (the final
        # rollback restores them) before exercising 273's down/up.
        for _v in ("net_position_v", "on_order_v", "committed_v", "consumption_v", "receipt_lead_v"):
            conn.execute(text(f"DROP VIEW IF EXISTS scm.{_v} CASCADE"))
        # Same reasoning one step further on. Migration 311 adds
        # `spo_allocations.po_line_id` referencing `purchase_order_lines`, which 273's
        # downgrade drops. In the real chain 311 downgrades first and removes the FK, so
        # this only bites because the test deliberately runs 273 out of order. Dropped
        # inside the savepoint, exactly like the views above, and restored by the rollback.
        conn.execute(text(
            "ALTER TABLE IF EXISTS spo_allocations "
            "DROP CONSTRAINT IF EXISTS fk_spo_allocations_po_line_id"
        ))
        ctx = MigrationContext.configure(conn)
        # Operations.context(ctx) installs the module-level `op` proxy the migration uses
        with Operations.context(ctx):
            mig.downgrade()
            gone = conn.execute(text(
                "select count(*) from information_schema.schemata where schema_name='scm'"
            )).scalar()
            assert gone == 0, "downgrade did not drop scm schema"
            mig.upgrade()
            back = conn.execute(text(
                "select count(*) from information_schema.tables where table_schema='scm'"
            )).scalar()
            assert back == len(SCM_TABLES), f"upgrade restored {back} tables, want {len(SCM_TABLES)}"
    finally:
        sp.rollback()
