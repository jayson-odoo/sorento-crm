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
import re
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


def _scratch_schemas(db) -> tuple[str, str]:
    """This `blank_session`'s own copies of the `scm` and `projects` schemas."""
    scratch = db.execute(text("select current_schema()")).scalar()
    return f"{scratch}_scm", f"{scratch}_projects"


def _rebind(sql: str, scm_schema: str, projects_schema: str) -> str:
    """A frozen body with its schema prefixes moved onto this session's scratch schemas -
    the same thing `schema_translate_map` does for the ORM."""
    return (
        sql.replace("scm.committed_v", f'"{scm_schema}".committed_v')
           .replace("projects.", f'"{projects_schema}".')
    )


#: A `scm.` / `projects.` prefix that survived `_rebind` - i.e. one still naming the SHARED
#: schema. The lookbehind lets through what a rebind produces (`"..._scm".committed_v`, the
#: quote) and what prose mentions (`app.services.scm.demand`, the dot).
_UNREBOUND = re.compile(r'(?<!["\w.])(scm|projects)\.')


class _ScratchOperations(Operations):
    """`alembic.op` for a `blank_session`, with every statement rebound onto the scratch
    schemas.

    A migration names `scm.committed_v` in full, so `search_path` cannot redirect it, and the
    DDL round trips below used to replay against the REAL view. On the shared test database
    that is live fire rather than a harmless rolled-back transaction: `DROP VIEW IF EXISTS
    scm.committed_v CASCADE` takes `scm.net_position_v` with it and holds an
    AccessExclusiveLock on BOTH for the length of the test, while every other xdist worker's
    `reorder_run_service._planning_rows` reads exactly those two. The two take them in
    opposite orders, so Postgres kills one - CI run 35293438670 reported "Process 447: DROP
    VIEW IF EXISTS scm.committed_v CASCADE" deadlocked against the plan query, and because
    `run_reorder` RECORDS a failure instead of raising, the victim
    (`test_reorder_committed_universe.py`) read an empty plan and failed on its own
    assertion with nothing on screen to point at the cause.

    The migration function itself is still what runs; only where its SQL lands moves.

    `_rebind` moves the two prefixes every body replayed here actually uses, so the guard
    below is what keeps that true: a migration added to this file later that names any OTHER
    real object fails loudly instead of quietly landing on the shared schema. 376's
    `_NET_POSITION_V` (`scm.net_position_v`, `scm.on_order_v`) is the live counter-example,
    a statement away from being replayed here.
    """

    def __init__(self, migration_context, scm_schema: str, projects_schema: str):
        super().__init__(migration_context)
        self._scm_schema = scm_schema
        self._projects_schema = projects_schema

    def execute(self, sqltext, *args, **kwargs):  # noqa: ANN001
        if isinstance(sqltext, str):
            sqltext = _rebind(sqltext, self._scm_schema, self._projects_schema)
            assert not _UNREBOUND.search(sqltext), (
                "this statement still names the SHARED schema, which is the deadlock this "
                f"file was repaired for - teach `_rebind` about it: {sqltext[:200]}"
            )
        return super().execute(sqltext, *args, **kwargs)


def _scratch_op(db) -> tuple[str, str]:
    """Point `alembic.op` at this session's scratch schemas, and name them."""
    import alembic.op as op_module

    scm_schema, projects_schema = _scratch_schemas(db)
    op_module._proxy = _ScratchOperations(
        MigrationContext.configure(db.connection()), scm_schema, projects_schema)
    return scm_schema, projects_schema


@pytest.fixture(autouse=True)
def _restore_alembic_proxy():
    """`alembic.op` holds its Operations object in a MODULE-level `_proxy`, so a test that
    points it at a scratch schema has to put it back, or every later test in this worker
    inherits a proxy bound to a closed connection and a schema that no longer exists. The
    attribute does not exist until something sets it, so putting it back can mean removing
    it again.
    """
    import alembic.op as op_module

    missing = object()
    before = getattr(op_module, "_proxy", missing)
    try:
        yield
    finally:
        if before is missing:
            if hasattr(op_module, "_proxy"):
                del op_module._proxy
        else:
            op_module._proxy = before


def _column_types(db, scm_schema: str) -> dict:
    """`committed_v`'s column names and their SQL types, straight from the catalogue.

    What `CREATE OR REPLACE VIEW` may not change, and therefore the thing a replacement has
    to keep identical.
    """
    return {
        name: type_
        for name, type_ in db.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'committed_v'"
        ), {"s": scm_schema}).all()
    }


def _view_body(db, scm_schema: str):
    """The installed body of `committed_v`, as Postgres reprints it."""
    return db.execute(text(
        "SELECT definition FROM pg_views "
        "WHERE schemaname = :s AND viewname = 'committed_v'"
    ), {"s": scm_schema}).scalar()


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
        "424_committed_v_project_oi_only",
        "426_committed_v_form_leg_scope",
        "428_order_inquiry_ack_state",
        "498_committed_v_bundled_qty",
        "511_committed_v_line_owed",
        "512_committed_v_redirect_exclude",
        "525_committed_v_orderback",
    ):
        imported = app_imports(_VERSIONS / f"{name}.py")
        assert imported == [], (
            f"{name} imports live application code ({', '.join(imported)}); freeze the "
            "SQL in the migration instead - a migration describes a point in history."
        )


@requires_pg
def test_newest_view_migration_matches_the_live_body():
    """Edit COMMITTED_V_SQL -> this goes red -> write a NEW migration with the new body.

    The newest one is `525_committed_v_orderback` (owner ruling 22 Sep 2026, SO417310 /
    MKT5529SS-DIY: an ORDER_BACK row is never capped by its borrowing line's outstanding),
    which replaces the body `512_committed_v_redirect_exclude` installed. Every superseded
    freeze stays exactly as it shipped, which is the whole point of the guard, so 512's,
    511's, 498's, 428's, 426's, 424's, 423's, 422's, 384's, 376's and 374's are checked
    below rather than updated here.
    """
    m525 = _load("525_committed_v_orderback")
    assert _normalize(m525._AS_OF_525) == _normalize(COMMITTED_V_SQL), (
        "app.services.scm.demand.COMMITTED_V_SQL changed. Do not edit migration 525; "
        "add a new migration that freezes the new body (525's pattern), so a from-zero "
        "replay stays true to history."
    )


@requires_pg
def test_512_still_freezes_the_body_it_shipped_with():
    """512's own distinguishing feature - the redirect exclusion - stays frozen exactly as
    it shipped, and 525's ORDER_BACK uncap (a later rule) must not have crept into it: 512
    still caps EVERY project row at its line's outstanding, order back or not.
    """
    m512 = _load("512_committed_v_redirect_exclude")
    assert "redirected_to_pool = FALSE" in m512._AS_OF_512
    assert "CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty" not in m512._AS_OF_512


@requires_pg
def test_511_still_freezes_the_body_it_shipped_with():
    """511's own distinguishing feature - the sales-order-line cap - stays frozen exactly
    as it shipped, and 512's redirect exclusion (a later rule) must not have crept into it.
    """
    m511 = _load("511_committed_v_line_owed")
    assert "LEAST(oir.qty, GREATEST(COALESCE(sol.qty_required" in m511._AS_OF_511
    assert "redirected_to_pool" not in m511._AS_OF_511


@requires_pg
def test_428_still_freezes_the_body_it_shipped_with():
    """428's own distinguishing feature: a REJECTED order inquiry row leaves both
    project legs, which is what 498 (bundled_qty) is layered on top of - the two must
    never be conflated, or a rejected AND bundled row's demand would be double-counted
    (or, going the other way, 428's rejection guard would silently vanish from history)."""
    m428 = _load("428_order_inquiry_ack_state")
    assert "oir.ack_state <> 'rejected'" in m428._AS_OF_428
    assert "bundled_qty" not in m428._AS_OF_428


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
    wrote. Seven links in the chain now: 374 restores 346, 376 restores 374 (`depends_on`
    puts 374 directly beneath it, so 346 would be a step too far back), 384 restores
    376 for the same reason, 422 restores 384, 423 restores 422, 424 restores 423, 426
    restores 424, 428 restores 426, 498 restores 428, 511 restores 498, 512 restores 511
    and 525 restores 512 (425, 427 and everything from 499 to 510 touch no view, so none
    of them is a link in this chain).
    """
    m346 = _load("346_scm_demand_origin_split")
    m374 = _load("374_so_supply_decisions")
    m376 = _load("376_scm_channel_read_model")
    m384 = _load("384_committed_v_line_decision")
    m422 = _load("422_committed_v_link_netting")
    m423 = _load("423_committed_v_form_rows")
    m424 = _load("424_committed_v_project_oi_only")
    m426 = _load("426_committed_v_form_leg_scope")
    m428 = _load("428_order_inquiry_ack_state")
    m498 = _load("498_committed_v_bundled_qty")
    m511 = _load("511_committed_v_line_owed")
    m512 = _load("512_committed_v_redirect_exclude")
    m525 = _load("525_committed_v_orderback")

    assert _normalize(m374._AS_OF_346) == _normalize(m346._AS_OF_346)
    assert _normalize(m376._AS_OF_374) == _normalize(m374._AS_OF_374)
    assert _normalize(m384._AS_OF_376) == _normalize(m376._AS_OF_376)
    assert _normalize(m422._AS_OF_384) == _normalize(m384._AS_OF_384)
    assert _normalize(m423._AS_OF_422) == _normalize(m422._AS_OF_422)
    assert _normalize(m424._AS_OF_423) == _normalize(m423._AS_OF_423)
    assert _normalize(m426._AS_OF_424) == _normalize(m424._AS_OF_424)
    assert _normalize(m428._AS_OF_426) == _normalize(m426._AS_OF_426)
    assert _normalize(m498._AS_OF_428) == _normalize(m428._AS_OF_428)
    assert _normalize(m511._AS_OF_498) == _normalize(m498._AS_OF_498)
    assert _normalize(m512._AS_OF_511) == _normalize(m511._AS_OF_511)
    assert _normalize(m525._AS_OF_512) == _normalize(m512._AS_OF_512)


@requires_pg
def test_the_proxy_refuses_a_statement_still_naming_the_shared_schema():
    """`_rebind` knows two prefixes, and the round trips below are only safe while every
    statement they replay uses one of them.

    376's `_NET_POSITION_V` is the live counter-example, a statement away from being
    replayed here: it names `scm.net_position_v` and `scm.on_order_v`, which `_rebind` does
    not move, so it would rebuild the SHARED view and take the AccessExclusiveLock that
    deadlocked a concurrent plan read (CI run 35293438670). The proxy refuses it instead of
    running it, and the refusal names the statement so the fix is obvious.
    """
    with blank_session() as db:
        _scratch_op(db)
        import alembic.op as op

        with pytest.raises(AssertionError, match=r"scm\.net_position_v"):
            op.execute("CREATE OR REPLACE VIEW scm.net_position_v AS SELECT 1 AS one")

        # Refused BEFORE it ran: the shared view is whatever it already was.
        assert db.execute(text(
            "SELECT definition FROM pg_views "
            "WHERE schemaname = 'scm' AND viewname = 'net_position_v'"
        )).scalar(), "the guard let the statement through to the real schema"


@requires_pg
def test_384_installs_the_line_rule_and_its_downgrade_puts_376_back():
    """Both directions, against a real database, inside a rolled-back transaction.

    A downgrade that leaves the newer body in place is worse than one that fails: the
    database would then be stamped at 376 while answering 384's question.
    """
    with blank_session() as db:
        scm_schema, projects = _scratch_op(db)
        m376 = _load("376_scm_channel_read_model")
        m384 = _load("384_committed_v_line_decision")
        db.execute(text(_rebind(m376._AS_OF_376, scm_schema, projects)))

        m384.upgrade()
        definition = _view_body(db, scm_schema)
        assert definition and "core_line_id" in definition

        m384.downgrade()
        restored = _view_body(db, scm_schema)
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
        scm_schema, projects = _scratch_op(db)
        m422 = _load("422_committed_v_link_netting")
        m423 = _load("423_committed_v_form_rows")
        db.execute(text(_rebind(m422._AS_OF_422, scm_schema, projects)))

        m423.upgrade()
        definition = _view_body(db, scm_schema)
        # Postgres reprints a view body with its own casts and parentheses, so the tell
        # is the ALIAS this leg introduces rather than the predicate as it was written.
        assert definition and "JOIN products fp" in definition

        m423.downgrade()
        restored = _view_body(db, scm_schema)
        assert restored and "JOIN products fp" not in restored
        # 422's own distinguishing feature, so a downgrade that installed some THIRD body
        # would not pass on the absence above alone.
        assert "lk.linked" in restored


@requires_pg
def test_424_replaces_423_in_place_and_changes_no_column_type():
    """CREATE OR REPLACE over the view that is ALREADY there, which is the only way to
    catch the failure this test exists for.

    424 turned three leg columns into bare constants, and a bare `0` is an integer, so
    `SUM(...)` came out bigint where the live column is numeric. Postgres refuses that:
    `cannot change data type of view column "unclassified_committed" from numeric to
    bigint`. It died on the captain's dev copy, not here, because every neighbour above
    DROPS the view first and a fresh CREATE may pick any types it likes.

    So this one installs 423's body and replaces it IN PLACE, and then reads the column
    types out of the catalogue - a body that widens or narrows one is the same outage under
    a different name.
    """
    with blank_session() as db:
        scm_schema, projects = _scratch_op(db)
        m423 = _load("423_committed_v_form_rows")
        m424 = _load("424_committed_v_project_oi_only")
        db.execute(text(_rebind(m423._AS_OF_423, scm_schema, projects)))
        before = _column_types(db, scm_schema)

        # No DROP in between: this is the statement the captain runs.
        m424.upgrade()
        assert _column_types(db, scm_schema) == before, "424 changed a column type"
        # And the newest link, over the body 424 leaves behind - same rule, same reason.
        _load("426_committed_v_form_leg_scope").upgrade()

        assert _column_types(db, scm_schema) == before, (
            "the replacement changed a column type, which Postgres refuses on any database "
            "that already carries the view"
        )
        definition = _view_body(db, scm_schema)
        # The tell of the new body: the book leg no longer speaks for project class.
        assert definition and "scm_order_inquiry" not in definition

        _load("426_committed_v_form_leg_scope").downgrade()
        m424.downgrade()
        assert _column_types(db, scm_schema) == before, "the downgrade changed a column type"
        restored = _view_body(db, scm_schema)
        assert restored and "scm_order_inquiry" in restored


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
        # scratch schemas - the same thing `schema_translate_map` does for the ORM, and the
        # same thing `_ScratchOperations` does for the DDL round trips above. Without it the
        # body would read the REAL `projects.order_inquiry_rows` and see none of the rows
        # below. The SQL is the live body either way, which is what is being asserted.
        scm_schema, projects = _scratch_schemas(db)
        body = _rebind(_load("423_committed_v_form_rows")._AS_OF_423, scm_schema, projects)
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
        # blank_session built today's model schema; put it back to the world as
        # migration 339 left it: the column 346 adds must not exist yet.
        db.execute(text("ALTER TABLE sales_orders DROP COLUMN IF EXISTS demand_origin"))
        # `scm` is schema-qualified in the view DDL, so `search_path` cannot redirect it and
        # the replay is rebound onto this session's scratch schema by hand. The scratch copy
        # carries no views at all, so the world 339 left is already what is there.
        scm_schema, _ = _scratch_op(db)

        _load("340_scm_committed_reads_the_decision").upgrade()

        # 346 adds demand_origin itself, then re-emits the view with the S13b clause.
        _load("346_scm_demand_origin_split").upgrade()

        definition = _view_body(db, scm_schema)
        assert definition and "demand_origin" in definition


@requires_pg
@pytest.mark.parametrize(
    "core_class, expected",
    [("retail", 10.0), ("project", 7.0)],
)
def test_a_form_row_and_the_line_it_names_are_counted_once_between_them(
    core_class, expected,
):
    """426: the book leg and the form leg may never both count the same requirement.

    One product at one warehouse, one open sales-order line of 10, and one decision-less
    inquiry row of 7 naming that line - the shape a CS Order Inquiry Form upload leaves
    behind.

    * a RETAIL line is the BOOK's to count, so the answer is its 10 and the row adds
      nothing. Between 424 and this migration it read 17.
    * a PROJECT line is nobody's on the book (P3), so the answer is the ROW's 7.

    Never 17, and never 0: exactly one leg speaks for the pair, and which one is decided by
    the class of the order the line belongs to.
    """
    with blank_session() as db:
        # Same schema rebinding as its neighbour above, and for the same reason: this is a
        # DATA assertion, so the body has to read THIS session's rows.
        scm_schema, projects = _scratch_schemas(db)
        body = _rebind(
            _load("426_committed_v_form_leg_scope")._AS_OF_426, scm_schema, projects)
        db.execute(text(f'DROP VIEW IF EXISTS "{scm_schema}".committed_v CASCADE'))
        db.execute(text(body))

        company = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        ids = {n: str(uuid.uuid4()) for n in
               ("cat", "uom", "product", "warehouse", "so", "sol", "pso", "psl",
                "inquiry", "row")}
        db.execute(text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, 'ZZTFL-CAT', 'ZZTFL-CAT')"), {"i": ids["cat"]})
        db.execute(text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name) "
            "VALUES (:i, 'ZZTFL-U', 'ZZTFL-U')"), {"i": ids["uom"]})
        db.execute(text(
            "INSERT INTO products (id, company_id, product_code, product_name, "
            "category_id, base_uom_id, list_price) "
            "VALUES (:i, :c, 'ZZTFL-ITEM', 'ZZTFL-ITEM', :cat, :uom, 0)"),
            {"i": ids["product"], "c": company, "cat": ids["cat"], "uom": ids["uom"]})
        db.execute(text(
            "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
            "is_active) VALUES (:i, :c, 'ZZTFL-WH', 'ZZTFL-WH', true)"),
            {"i": ids["warehouse"], "c": company})
        db.execute(text(
            "INSERT INTO sales_orders (id, company_id, so_number, status, demand_class, "
            "created_at, updated_at) "
            "VALUES (:i, :c, 'ZZTFL-SO', 'open', :dc, now(), now())"),
            {"i": ids["so"], "c": company, "dc": core_class})
        db.execute(text(
            "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_delivered, line_status, purchasing_status, created_at, "
            "updated_at) VALUES (:i, :so, :p, :w, 10, 0, 'open', 'needs_purchase', now(), "
            "now())"),
            {"i": ids["sol"], "so": ids["so"], "p": ids["product"],
             "w": ids["warehouse"]})
        db.execute(text(
            "INSERT INTO " + projects + ".sales_orders (id, company_id, provisional_ref, "
            "status, created_at, updated_at) "
            "VALUES (:i, :c, 'ZZTFL-PSO', 'adopted', now(), now())"),
            {"i": ids["pso"], "c": company})
        db.execute(text(
            "INSERT INTO " + projects + ".sales_order_lines (id, company_id, "
            "project_sales_order_id, line_no, qty, unit_price, amount, product_id, "
            "core_sales_order_line_id, created_at) "
            "VALUES (:i, :c, :p, 1, 10, 0, 0, :prod, :core, now())"),
            {"i": ids["psl"], "c": company, "p": ids["pso"], "prod": ids["product"],
             "core": ids["sol"]})
        db.execute(text(
            "INSERT INTO " + projects + ".order_inquiries (id, company_id, inquiry_no, "
            "project_sales_order_id, state, raised_at) "
            "VALUES (:i, :c, 'OI-ZZTFL', :p, 'raised', now())"),
            {"i": ids["inquiry"], "c": company, "p": ids["pso"]})
        # No supply decision: the CS form raises this itself, which is what puts it in the
        # form leg rather than the confirmed one.
        db.execute(text(
            "INSERT INTO " + projects + ".order_inquiry_rows (id, company_id, "
            "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, state, "
            "redirected_to_pool, created_at) "
            "VALUES (:i, :c, :inq, :l, 'ZZTFL-ITEM', 7, 'ORDER_BACK', 'ZZTFL-WH', "
            "'raised', false, now())"),
            {"i": ids["row"], "c": company, "inq": ids["inquiry"], "l": ids["psl"]})
        db.flush()

        counted = db.execute(text(
            f'SELECT committed FROM "{scm_schema}".committed_v '
            "WHERE product_id = :p AND warehouse_id = :w"),
            {"p": ids["product"], "w": ids["warehouse"]}).scalar()

        assert float(counted or 0) == expected


# =============================================================================
# AC-OB-4/5/6 (`PLAN-oi-order-back-not-capped.md`) - the CONFIRMED leg's own arithmetic:
# an ORDER_BACK row is owed in full, at the DONOR warehouse its `stock_location` names,
# even when the borrowing line it hangs off is delivered in full; the sibling ORDER row
# on the SAME line stays capped at 0 (7.3, unchanged). Live `COMMITTED_V_SQL`, installed
# fresh into a scratch schema the same way 423's/426's own data tests above do.
# =============================================================================


def _ob_confirmed_leg_world(db, projects: str, *, bundled_qty=0, link_qty=None):
    """One product, two warehouses - the borrowing line's OWN, and the DONOR
    `stock_location` names - one core sales-order line delivered in full (3/3, nothing
    outstanding), its mirror, an ACTIVE supply decision, and two sibling confirmed-leg
    rows on that one line: an ORDER_BACK of qty 3 and an ORDER of qty 3. Both rows share
    the decision (`so_supply_decisions` allows only one active revision per PSO).
    """
    import json

    company = db.execute(text("select id from companies where code = 'SRT'")).scalar()
    ids = {n: str(uuid.uuid4()) for n in (
        "cat", "uom", "product", "own_wh", "donor_wh", "core_so", "core_line", "pso",
        "mirror", "inquiry", "decision", "order_back_row", "order_row",
    )}
    own_code = f"ZZTOB-OWN-{ids['own_wh'][:6]}"
    donor_code = f"ZZTOB-DONOR-{ids['donor_wh'][:6]}"
    item_code = f"ZZTOB-P-{ids['product'][:6]}"

    db.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (:i, :c, :c)"), {"i": ids["cat"], "c": f"ZZTOB-CAT-{ids['cat'][:6]}"})
    db.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
        {"i": ids["uom"], "c": f"ZZTOB-U-{ids['uom'][:6]}"})
    db.execute(text(
        "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
        "base_uom_id, list_price) VALUES (:i, :c, :code, :code, :cat, :uom, 0)"),
        {"i": ids["product"], "c": company, "code": item_code, "cat": ids["cat"],
         "uom": ids["uom"]})
    db.execute(text(
        "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
        "is_active) VALUES (:i, :c, :code, :code, true)"),
        {"i": ids["own_wh"], "c": company, "code": own_code})
    db.execute(text(
        "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
        "is_active) VALUES (:i, :c, :code, :code, true)"),
        {"i": ids["donor_wh"], "c": company, "code": donor_code})
    db.execute(text(
        "INSERT INTO sales_orders (id, company_id, so_number, status, demand_class) "
        "VALUES (:i, :c, :n, 'open', 'project')"),
        {"i": ids["core_so"], "c": company, "n": f"ZZTOB-SO-{ids['core_so'][:8]}"})
    # Delivered in full: qty_ordered == qty_delivered, so `_LINE_OUTSTANDING_SQL` is 0 -
    # the exact shape SO417310 line 16 carries (plan section 2).
    db.execute(text(
        "INSERT INTO sales_order_lines (id, company_id, sales_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_delivered, unit_price, line_status) "
        "VALUES (:i, :c, :so, :p, :w, 3, 3, 0, 'closed')"),
        {"i": ids["core_line"], "c": company, "so": ids["core_so"], "p": ids["product"],
         "w": ids["own_wh"]})
    db.execute(text(
        "INSERT INTO " + projects + ".sales_orders (id, company_id, provisional_ref, "
        "so_id, status, created_at, updated_at) "
        "VALUES (:i, :c, :ref, :so, 'published', now(), now())"),
        {"i": ids["pso"], "c": company, "ref": f"ZZTOB-PSO-{ids['pso'][:8]}",
         "so": ids["core_so"]})
    db.execute(text(
        "INSERT INTO " + projects + ".sales_order_lines (id, company_id, "
        "project_sales_order_id, line_no, product_id, qty, unit_price, amount, "
        "core_sales_order_line_id, created_at) "
        "VALUES (:i, :c, :p, 1, :prod, 3, 0, 0, :core, now())"),
        {"i": ids["mirror"], "c": company, "p": ids["pso"], "prod": ids["product"],
         "core": ids["core_line"]})
    db.execute(text(
        "INSERT INTO " + projects + ".order_inquiries (id, company_id, inquiry_no, "
        "project_sales_order_id, state, raised_at) "
        "VALUES (:i, :c, :no, :p, 'raised', now())"),
        {"i": ids["inquiry"], "c": company, "no": f"OI-ZZTOB-{ids['inquiry'][:6]}",
         "p": ids["pso"]})
    db.execute(text(
        "INSERT INTO " + projects + ".so_supply_decisions (id, company_id, "
        "project_sales_order_id, revision_no, state, line_snapshots, confirmed_at) "
        "VALUES (:i, :c, :p, 1, 'active', CAST(:snap AS jsonb), now())"),
        {"i": ids["decision"], "c": company, "p": ids["pso"],
         "snap": json.dumps([{"line_no": 1}])})
    db.execute(text(
        "INSERT INTO " + projects + ".order_inquiry_rows (id, company_id, "
        "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, state, "
        "ack_state, supply_decision_id, bundled_qty, redirected_to_pool, created_at) "
        "VALUES (:i, :c, :inq, :l, :code, 3, 'ORDER_BACK', :loc, 'raised', "
        "'acknowledged', :d, :bundled, false, now())"),
        {"i": ids["order_back_row"], "c": company, "inq": ids["inquiry"],
         "l": ids["mirror"], "code": item_code, "loc": donor_code, "d": ids["decision"],
         "bundled": bundled_qty})
    db.execute(text(
        "INSERT INTO " + projects + ".order_inquiry_rows (id, company_id, "
        "order_inquiry_id, so_line_id, item_code, qty, verb, state, ack_state, "
        "supply_decision_id, redirected_to_pool, created_at) "
        "VALUES (:i, :c, :inq, :l, :code, 3, 'ORDER', 'raised', 'acknowledged', :d, "
        "false, now())"),
        {"i": ids["order_row"], "c": company, "inq": ids["inquiry"], "l": ids["mirror"],
         "code": item_code, "d": ids["decision"]})
    db.flush()

    if link_qty is not None:
        supplier, po, po_line = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        db.execute(text(
            "INSERT INTO suppliers (id, company_id, supplier_code, supplier_name, "
            "is_active) VALUES (:i, :c, :code, :code, true)"),
            {"i": supplier, "c": company, "code": f"ZZTOB-S-{supplier[:6]}"})
        db.execute(text(
            "INSERT INTO purchase_orders (id, company_id, po_number, supplier_id, "
            "issue_date, status) VALUES (:i, :c, :n, :s, current_date, 'active')"),
            {"i": po, "c": company, "n": f"ZZTOB-PO-{po[:8]}", "s": supplier})
        db.execute(text(
            "INSERT INTO purchase_order_lines (id, company_id, purchase_order_id, "
            "product_id, warehouse_id, qty_ordered, qty_received, line_status, "
            "expected_date) VALUES (:i, :c, :po, :p, :w, 5, 0, 'open', current_date)"),
            {"i": po_line, "c": company, "po": po, "p": ids["product"],
             "w": ids["donor_wh"]})
        db.execute(text(
            "INSERT INTO " + projects + ".order_inquiry_links (id, company_id, "
            "row_id, po_line_id, document, qty, auto, created_at) "
            "VALUES (:i, :c, :r, :pl, 'ZZTOB-LINKED', :q, false, now())"),
            {"i": str(uuid.uuid4()), "c": company, "r": ids["order_back_row"],
             "pl": po_line, "q": link_qty})
        db.flush()

    return {"product": ids["product"], "own_code": own_code, "donor_code": donor_code}


def _ob_committed_by_warehouse(db, scm_schema: str, product_id: str) -> dict:
    rows = db.execute(text(
        "SELECT w.warehouse_code, cv.project_committed "
        f'FROM "{scm_schema}".committed_v cv '
        "LEFT JOIN warehouses w ON w.id = cv.warehouse_id "
        "WHERE cv.product_id = :p"), {"p": product_id}).all()
    return {code: float(qty) for code, qty in rows}


@requires_pg
def test_ac_ob_4_an_order_back_row_counts_in_full_at_its_donor_warehouse():
    """AC-OB-4 (R2). An ORDER_BACK row on a core line delivered 3/3 (nothing outstanding)
    still counts its own qty 3 - the 14 Sep cap (7.3) belongs to a fresh ORDER only - and
    it counts at the DONOR warehouse its `stock_location` names, not the borrowing line's
    own warehouse."""
    with blank_session() as db:
        scm_schema, projects = _scratch_schemas(db)
        db.execute(text(f'DROP VIEW IF EXISTS "{scm_schema}".committed_v CASCADE'))
        db.execute(text(_rebind(COMMITTED_V_SQL, scm_schema, projects)))

        world = _ob_confirmed_leg_world(db, projects)
        by_wh = _ob_committed_by_warehouse(db, scm_schema, world["product"])

        assert by_wh.get(world["donor_code"]) == 3.0, by_wh


@requires_pg
def test_ac_ob_5_an_order_row_on_the_same_delivered_line_stays_capped_at_zero():
    """AC-OB-5, the sibling of AC-OB-4 on the SAME delivered line: the 14 Sep cap
    (SO368872 / SRTWC286-SH) is unchanged for a plain ORDER row, and it counts at the
    line's OWN warehouse, never the donor."""
    with blank_session() as db:
        scm_schema, projects = _scratch_schemas(db)
        db.execute(text(f'DROP VIEW IF EXISTS "{scm_schema}".committed_v CASCADE'))
        db.execute(text(_rebind(COMMITTED_V_SQL, scm_schema, projects)))

        world = _ob_confirmed_leg_world(db, projects)
        by_wh = _ob_committed_by_warehouse(db, scm_schema, world["product"])

        assert by_wh.get(world["own_code"], 0.0) == 0.0, by_wh


@requires_pg
def test_ac_ob_6_an_order_back_row_nets_its_own_linked_and_bundled_quantity():
    """AC-OB-6. An ORDER_BACK row of qty 3, with 1 already linked to a purchase-order
    line and 1 bundled into a companion's own line, counts 1 - never capped, but still
    netted against what is already placed or already riding on something else."""
    with blank_session() as db:
        scm_schema, projects = _scratch_schemas(db)
        db.execute(text(f'DROP VIEW IF EXISTS "{scm_schema}".committed_v CASCADE'))
        db.execute(text(_rebind(COMMITTED_V_SQL, scm_schema, projects)))

        world = _ob_confirmed_leg_world(db, projects, bundled_qty=1, link_qty=1)
        by_wh = _ob_committed_by_warehouse(db, scm_schema, world["product"])

        assert by_wh.get(world["donor_code"]) == 1.0, by_wh
