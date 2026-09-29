"""Migration `cpc4_cost_packaging_method` (#1288 round 8, AC-PK-03): up, down, up with data.

The owner's ruling of 28 Sep 2026 makes a cost per packaging method: a line's bracket note
(`code_note`) becomes its `packaging_method`, a plain code is `standard`, and a cost row takes its
source line's packaging. Run through a real alembic `Operations` context against scratch copies
of the two tables on a scratch schema, reached through `search_path` (the migration names the
tables unqualified): DDL on the shared tables would lock them for every other worker (lesson 114).
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
    Path(__file__).resolve().parent / ".." / "alembic" / "versions" / "cpc4_cost_packaging_method.py"
).resolve()


def _load():
    spec = importlib.util.spec_from_file_location("m_cpc4", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _cols(conn, schema: str, table: str) -> set[str]:
    return {
        r[0] for r in conn.execute(
            sa.text("SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"),
            {"s": schema, "t": table},
        )
    }


def _indexes(conn, schema: str) -> set[str]:
    return {
        r[0] for r in conn.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = 'product_supplier_costs'"),
            {"s": schema},
        )
    }


def test_revision_fits_alembic_version_and_sits_on_cpc3():
    module = _load()
    assert module.revision == "cpc4_cost_packaging_method"
    assert len(module.revision) <= 32
    assert module.down_revision == "cpc3_lead_time_nullable"


def test_frozen_key_matches_the_service_rule():
    from app.services.procurement.supplier_cost_service import packaging_key

    module = _load()
    for value in ("OPP", " opp ", "ＯＰＰ", "彩盒", "", None, "Big  Box"):
        assert module._key(value) == packaging_key(value), value


def test_up_down_up_with_data_on_scratch_tables():
    module = _load()
    scratch = f"zzs_mig_cpc4_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{scratch}"')
            conn.exec_driver_sql(
                "CREATE TABLE cost_price_change_lines (id int PRIMARY KEY, supplier_code varchar(255), "
                "code_note varchar(255))"
            )
            conn.exec_driver_sql(
                "CREATE TABLE product_supplier_costs (id int PRIMARY KEY, product_supplier_id int, "
                "unit_cost numeric(12,2), start_date date, source_change_line_id int)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_product_supplier_costs_link_start ON product_supplier_costs "
                "(product_supplier_id, start_date)"
            )
            conn.exec_driver_sql(
                "INSERT INTO cost_price_change_lines VALUES "
                "(1, 'CB2500SS-BL', '彩盒'), (2, 'CB2500SS-BL-DIY', 'OPP'), (3, 'CB2500SS-BL-DIY', ' 吊卡 '), "
                "(4, 'PLAIN', NULL), (5, 'BLANK', '')"
            )
            conn.exec_driver_sql(
                "INSERT INTO product_supplier_costs VALUES "
                "(10, 1, 9.50, NULL, 1), (11, 2, 9.90, NULL, 2), (12, 2, 9.40, NULL, 3), "
                "(13, 3, 5.00, NULL, 4), (14, 3, 6.00, NULL, NULL)"
            )

            def check_up():
                lines = {
                    r[0]: (r[1], r[2]) for r in conn.exec_driver_sql(
                        "SELECT id, packaging_method, packaging_key FROM cost_price_change_lines"
                    )
                }
                assert lines == {
                    1: ("彩盒", "彩盒"), 2: ("OPP", "opp"), 3: ("吊卡", "吊卡"),
                    4: ("standard", "standard"), 5: ("standard", "standard"),
                }
                costs = {
                    r[0]: (r[1], r[2]) for r in conn.exec_driver_sql(
                        "SELECT id, packaging_method, packaging_key FROM product_supplier_costs"
                    )
                }
                assert costs == {
                    10: ("彩盒", "彩盒"), 11: ("OPP", "opp"), 12: ("吊卡", "吊卡"),
                    13: ("standard", "standard"), 14: ("standard", "standard"),
                }
                assert "code_note" not in _cols(conn, scratch, "cost_price_change_lines")
                assert _indexes(conn, scratch) >= {"ix_product_supplier_costs_link_packaging"}
                assert "ix_product_supplier_costs_link_start" not in _indexes(conn, scratch)

            _run(conn, module.upgrade)
            check_up()
            _run(conn, module.upgrade)  # idempotent
            check_up()

            _run(conn, module.downgrade)
            notes = dict(conn.exec_driver_sql("SELECT id, code_note FROM cost_price_change_lines").all())
            assert notes == {1: "彩盒", 2: "OPP", 3: "吊卡", 4: None, 5: None}
            assert not {"packaging_method", "packaging_key"} & _cols(conn, scratch, "product_supplier_costs")
            assert "ix_product_supplier_costs_link_start" in _indexes(conn, scratch)
            _run(conn, module.downgrade)  # idempotent

            _run(conn, module.upgrade)
            check_up()
        finally:
            outer.rollback()
