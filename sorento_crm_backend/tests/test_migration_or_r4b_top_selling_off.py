"""REPORT-SMART-L R4b (AC-OR4): the migration that takes `crm_top_selling_report` off every
chatbot_domains row and puts `crm_report_ask` on the sales row. A `test_migration_*` file: serial in CI.
Builds its own rows; never relies on the DB head.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa

from tests._pg_fixture import blank_session

_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
OLD = "crm_top_selling_report"
ASK = "crm_report_ask"


def _load(name: str, filename: str):
    if str(_VERSIONS.parent) not in sys.path:
        sys.path.insert(0, str(_VERSIONS.parent))
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, module, direction="upgrade"):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _tools(db, name):
    return db.execute(sa.text("SELECT tools FROM chatbot_domains WHERE name = :n"), {"n": name}).scalar()


def _seed(db):
    s0 = _load("_zzt_r4b_s0", "chatbot_rearch_s0.py")
    s0.seed_domains_and_kinds(db.connection().execution_options(compiled_cache=None))
    has_sales = db.execute(sa.text("SELECT 1 FROM chatbot_domains WHERE name = 'sales'")).scalar()
    if not has_sales:
        cols = [r[0] for r in db.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'chatbot_domains' "
            "AND table_schema = current_schema() AND column_name NOT IN ('id', 'name')"))]
        col_list = ", ".join(f'"{c}"' for c in cols)
        db.execute(sa.text(
            f"INSERT INTO chatbot_domains (id, name, {col_list}) "
            f"SELECT gen_random_uuid(), 'sales', {col_list} FROM chatbot_domains WHERE name = 'order'"))
    set_sql = sa.text("UPDATE chatbot_domains SET tools = CAST(:t AS text[]) WHERE name = :n")
    db.execute(set_sql, {"n": "order", "t": ["crm_zz_orders", OLD, ASK]})
    db.execute(set_sql, {"n": "sales", "t": ["crm_sales_report", "crm_sales_analysis", OLD]})
    other = db.execute(sa.text(
        "SELECT name FROM chatbot_domains WHERE name NOT IN ('order', 'sales') ORDER BY name LIMIT 1")).scalar()
    db.execute(set_sql, {"n": other, "t": ["crm_zz_other", OLD]})
    return other


def test_upgrade_removes_old_tool_everywhere_and_adds_ask_to_sales_once():
    with blank_session() as db:
        other = _seed(db)
        mod = _load("_zzt_r4b", "or_r4b_top_selling_off.py")
        _run(db, mod)
        assert _tools(db, "order") == ["crm_zz_orders", ASK]
        assert _tools(db, "sales") == ["crm_sales_report", "crm_sales_analysis", ASK]
        assert _tools(db, other) == ["crm_zz_other"]
        _run(db, mod)
        assert _tools(db, "sales") == ["crm_sales_report", "crm_sales_analysis", ASK]
        assert _tools(db, "order") == ["crm_zz_orders", ASK]


def test_apply_tools_is_idempotent_and_leaves_no_row_with_the_old_tool():
    with blank_session() as db:
        _seed(db)
        mod = _load("_zzt_r4b_b", "or_r4b_top_selling_off.py")
        mod.apply_tools(db.connection())
        mod.apply_tools(db.connection())
        left = db.execute(sa.text(
            "SELECT name FROM chatbot_domains WHERE CAST(:t AS text) = ANY(tools)"), {"t": OLD}).all()
        assert left == []
        assert _tools(db, "sales").count(ASK) == 1


def test_downgrade_restores_old_tool_where_it_was_and_removes_ask_from_sales():
    with blank_session() as db:
        other = _seed(db)
        mod = _load("_zzt_r4b_c", "or_r4b_top_selling_off.py")
        _run(db, mod)
        _run(db, mod, "downgrade")
        assert OLD in _tools(db, "order")
        assert ASK in _tools(db, "order")  # the order row had it before: untouched
        assert OLD in _tools(db, "sales")
        assert ASK not in _tools(db, "sales")  # the sales row did not have it before
        assert OLD in _tools(db, other)


def test_revision_id_fits_and_chains():
    mod = _load("_zzt_r4b_d", "or_r4b_top_selling_off.py")
    assert mod.revision == "or_r4b_top_selling_off"
    assert len(mod.revision) <= 32
