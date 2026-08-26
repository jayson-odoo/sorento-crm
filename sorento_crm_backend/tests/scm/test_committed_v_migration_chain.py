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
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.services.scm.demand import COMMITTED_V_SQL
from tests._migration_imports import app_imports
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
    """No migration may import the live application code - that import IS the outage.

    Wider than the view chain the file is named for: `374_uom_decimal_places` adds
    `units_of_measure.decimal_places` and BACKFILLS it, and it originally called
    `app.services.uom_decimal_places.backfill_uom_decimal_places` - the same shape as the
    340/346 failure, with the same replay hazard. Its name lists and observed-scale SQL are
    frozen in the migration now, and the service keeps the live copy for admin re-runs.

    The list is the union of both SCM lanes: Stage 1C's `374_so_supply_decisions` and
    Stage 2's `374_uom_decimal_places` / `376_scm_channel_read_model`. Two different
    revisions numbered 374 is not a typo - they are siblings off `373_merge_scm_stage0_1a`.
    """
    for name in (
        "340_scm_committed_reads_the_decision",
        "346_scm_demand_origin_split",
        "374_so_supply_decisions",
        "374_uom_decimal_places",
        "376_scm_channel_read_model",
        "384_committed_v_line_decision",
    ):
        imported = app_imports(_VERSIONS / f"{name}.py")
        assert imported == [], (
            f"{name} imports live application code ({', '.join(imported)}); freeze the "
            "SQL in the migration instead - a migration describes a point in history."
        )


@requires_pg
def test_newest_view_migration_matches_the_live_body():
    """Edit COMMITTED_V_SQL -> this goes red -> write a NEW migration with the new body.

    The newest one is `423_committed_v_form_rows` (a leg for the instruction the Order
    Inquiry Form raised with no sales-order line to read a product or a location off),
    which replaces the body `422_committed_v_link_netting` installed. Every superseded
    freeze stays exactly as it shipped, which is the whole point of the guard, so 422's,
    384's, 376's and 374's are checked below rather than updated here.
    """
    m423 = _load("423_committed_v_form_rows")
    assert _normalize(m423._AS_OF_423) == _normalize(COMMITTED_V_SQL), (
        "app.services.scm.demand.COMMITTED_V_SQL changed. Do not edit migration 423; "
        "add a new migration that freezes the new body (423's pattern), so a from-zero "
        "replay stays true to history."
    )


@requires_pg
def test_376_still_freezes_the_body_it_shipped_with():
    """The channel split's body is history now, and history does not move.

    Pinned by its distinguishing feature in both directions: 376 excludes a whole ORDER
    the moment any decision exists, which is exactly what 384 replaces, and it must not
    quietly acquire the line-level rule.
    """
    m376 = _load("376_scm_channel_read_model")
    assert "dd.sales_order_id = so.id" in m376._AS_OF_376
    assert "core_line_id" not in m376._AS_OF_376


@requires_pg
def test_346_still_freezes_the_body_it_shipped_with():
    """A superseded freeze is history and must stay verbatim.

    346's body is what a database at that revision holds; editing it to match today's rule
    would change the replay without changing any existing database, which is the same
    mistake in the other direction from importing live code.
    """
    m346 = _load("346_scm_demand_origin_split")
    assert "demand_origin = 'scm_order_inquiry'" in m346._AS_OF_346
    assert "project_committed" not in m346._AS_OF_346


@requires_pg
def test_every_downgrade_copy_matches_the_revision_it_restores():
    """A downgrade restores the body of the revision BELOW it, copied verbatim.

    Each view migration keeps its own frozen copy of the body it replaced, so the copies
    have to be pinned equal to the originals or a downgrade quietly installs a body nobody
    wrote. Five links in the chain now: 374 restores 346, 376 restores 374 (`depends_on`
    puts 374 directly beneath it, so 346 would be a step too far back), 384 restores
    376 for the same reason, 422 restores 384 and 423 restores 422.
    """
    m346 = _load("346_scm_demand_origin_split")
    m374 = _load("374_so_supply_decisions")
    m376 = _load("376_scm_channel_read_model")
    m384 = _load("384_committed_v_line_decision")
    m422 = _load("422_committed_v_link_netting")
    m423 = _load("423_committed_v_form_rows")

    assert _normalize(m374._AS_OF_346) == _normalize(m346._AS_OF_346)
    assert _normalize(m376._AS_OF_374) == _normalize(m374._AS_OF_374)
    assert _normalize(m384._AS_OF_376) == _normalize(m376._AS_OF_376)
    assert _normalize(m422._AS_OF_384) == _normalize(m384._AS_OF_384)
    assert _normalize(m423._AS_OF_422) == _normalize(m422._AS_OF_422)


@requires_pg
def test_384_installs_the_line_rule_and_its_downgrade_puts_376_back():
    """Both directions, against a real database, inside a rolled-back transaction.

    A downgrade that leaves the newer body in place is worse than one that fails: the
    database would then be stamped at 376 while answering 384's question.
    """
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        db.execute(text("DROP VIEW IF EXISTS scm.committed_v CASCADE"))

        m376 = _load("376_scm_channel_read_model")
        m384 = _load("384_committed_v_line_decision")
        db.execute(text(m376._AS_OF_376))

        conn = db.connection()
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as op_module

        op_module._proxy = ops
        m384.upgrade()
        definition = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert definition and "core_line_id" in definition

        m384.downgrade()
        restored = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert restored and "core_line_id" not in restored
        assert "dd.sales_order_id = so.id" in restored


@requires_pg
def test_423_installs_the_form_leg_and_its_downgrade_puts_422_back():
    """The leg that counts an instruction with no sales-order line, both directions.

    An Order Inquiry Form row for a quantity AutoCount has closed has no `so_line_id` and no
    supply decision, which is what both existing confirmed legs join on - so before this the
    row was raised, shown to purchasing, and invisible to the plan. The tell is the join to
    `products` on the row's own item code, which no earlier body makes.
    """
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        db.execute(text("DROP VIEW IF EXISTS scm.committed_v CASCADE"))

        m422 = _load("422_committed_v_link_netting")
        m423 = _load("423_committed_v_form_rows")
        db.execute(text(m422._AS_OF_422))

        conn = db.connection()
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as op_module

        op_module._proxy = ops
        m423.upgrade()
        definition = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        # Postgres reprints a view body with its own casts and parentheses, so the tell
        # is the ALIAS this leg introduces rather than the predicate as it was written.
        assert definition and "JOIN products fp" in definition

        m423.downgrade()
        restored = db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'committed_v'"
        )).scalar()
        assert restored and "JOIN products fp" not in restored
        # 422's own distinguishing feature, so a downgrade that installed some THIRD body
        # would not pass on the absence above alone.
        assert "lk.linked" in restored


@requires_pg
def test_the_form_leg_counts_a_row_with_no_line_and_never_one_that_has_one():
    """The whole arithmetic of the new leg, on one product, in one place.

    Three rows, and the reason each is or is not counted:

    * `so_line_id IS NULL` - the fixture's `[NL]` shape. Counted HERE, at the row's own item
      code and stock location, because nothing else counts it: the line its quantity came
      from was closed in AutoCount and no decision points at it.
    * `so_line_id` set - counted by the SHEET leg at that line, and NOT here. Adding the row
      on top of the line it belongs to is the same quantity twice, and the planner buys it
      twice.
    * no stock location - still demand, still in the view, at a NULL warehouse that every
      reader's `(product, warehouse)` join matches nowhere. Counted at no location rather
      than invented at one, and present rather than dropped.
    """
    with blank_session() as db:
        # The view body under test, with its SCHEMA PREFIXES rebound onto this session's
        # scratch schemas - the same thing `schema_translate_map` does for the ORM. The
        # neighbours above drop and rebuild the REAL `scm.committed_v` inside a rolled-back
        # transaction, which is fine for a DDL round trip and no use at all for a DATA one:
        # the body would read the REAL `projects.order_inquiry_rows` and see none of the
        # rows below. The SQL is the live body either way, which is what is being asserted.
        scratch = db.execute(text("select current_schema()")).scalar()
        projects = f"{scratch}_projects"
        scm_schema = f"{scratch}_scm"
        body = (
            _load("423_committed_v_form_rows")._AS_OF_423
            .replace("scm.committed_v", f'"{scm_schema}".committed_v')
            .replace("projects.", f'"{projects}".')
        )
        db.execute(text(f'DROP VIEW IF EXISTS "{scm_schema}".committed_v CASCADE'))
        db.execute(text(body))

        company = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        ids = {name: str(uuid.uuid4()) for name in
               ("cat", "uom", "product", "warehouse", "pso", "inquiry", "a", "b", "c")}
        db.execute(text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, 'ZZTCV-CAT', 'ZZTCV-CAT')"), {"i": ids["cat"]})
        db.execute(text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name) "
            "VALUES (:i, 'ZZTCV-U', 'ZZTCV-U')"), {"i": ids["uom"]})
        db.execute(text(
            "INSERT INTO products (id, company_id, product_code, product_name, "
            "category_id, base_uom_id, list_price) "
            "VALUES (:i, :c, 'ZZTCV-ITEM', 'ZZTCV-ITEM', :cat, :uom, 0)"),
            {"i": ids["product"], "c": company, "cat": ids["cat"], "uom": ids["uom"]})
        db.execute(text(
            "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
            "is_active) VALUES (:i, :c, 'ZZTCV-WH', 'ZZTCV-WH', true)"),
            {"i": ids["warehouse"], "c": company})
        db.execute(text(
            "INSERT INTO " + projects + ".sales_orders (id, company_id, provisional_ref, status, "
            "created_at, updated_at) VALUES (:i, :c, 'ZZTCV-PSO', 'adopted', now(), now())"),
            {"i": ids["pso"], "c": company})
        db.execute(text(
            "INSERT INTO " + projects + ".order_inquiries (id, company_id, inquiry_no, "
            "project_sales_order_id, state, raised_at) "
            "VALUES (:i, :c, 'OI-ZZTCV', :p, 'raised', now())"),
            {"i": ids["inquiry"], "c": company, "p": ids["pso"]})
        db.execute(text(
            "INSERT INTO " + projects + ".sales_order_lines (id, company_id, "
            "project_sales_order_id, line_no, qty, unit_price, amount, product_id, "
            "created_at) VALUES (:i, :c, :p, 1, 5, 0, 0, :prod, now())"),
            {"i": ids["c"], "c": company, "p": ids["pso"], "prod": ids["product"]})

        def _row(row_id, *, location, so_line=None):
            db.execute(text(
                "INSERT INTO " + projects + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, "
                "state, redirected_to_pool, created_at) "
                "VALUES (:i, :c, :inq, :l, 'ZZTCV-ITEM', 7, 'ORDER_BACK', :loc, "
                "'raised', false, now())"),
                {"i": row_id, "c": company, "inq": ids["inquiry"], "l": so_line,
                 "loc": location})

        _row(ids["a"], location="ZZTCV-WH")
        _row(ids["b"], location="ZZTCV-WH", so_line=ids["c"])
        _row(ids["c"], location=None)
        db.flush()

        counted = db.execute(text(
            "SELECT w.warehouse_code, cv.project_committed "
            f'FROM "{scm_schema}".committed_v cv '
            "LEFT JOIN warehouses w ON w.id = cv.warehouse_id "
            "WHERE cv.product_id = :p"), {"p": ids["product"]}).all()
        by_location = {code: float(qty) for code, qty in counted}

        # Row a only. Row b belongs to a line the sheet leg counts, row c has no location.
        assert by_location.get("ZZTCV-WH") == 7.0
        # Present, at no warehouse, rather than dropped or attributed to somebody.
        assert by_location.get(None) == 7.0


@requires_pg
def test_replaying_340_then_346_on_a_339_shaped_schema():
    """The exact production failure path: 340 before demand_origin exists, then 346."""
    with blank_session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        # blank_session built today's model schema; put it back to the world as
        # migration 339 left it: the column 346 adds must not exist yet.
        db.execute(text("ALTER TABLE sales_orders DROP COLUMN IF EXISTS demand_origin"))
        # `scm` is schema-qualified in the view DDL, so the replay lands on the REAL view
        # (inside this rolled-back transaction). It has since grown the channel columns,
        # and Postgres refuses a CREATE OR REPLACE that DROPS columns - so the world 339
        # left needs the view genuinely absent, not merely out of date.
        db.execute(text("DROP VIEW IF EXISTS scm.committed_v CASCADE"))

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
