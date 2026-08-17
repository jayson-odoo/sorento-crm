"""S2-BE-3: the channel-aware read model (PLAN-scm-front-planning.md 6.4, 3.5, 4).

`scm.committed_v` today emits one aggregate `committed` column per (product_id,
warehouse_id). This slice adds `project_committed`, `retail_committed` and
`unclassified_committed` to that SAME row, so `committed` stays their sum and every existing
consumer (`scm.net_position_v`, the reorder engine) keeps its cardinality and join keys.

Classification is `sales_orders.demand_class`, never location (AC-E01, AC-E02):

* `demand_class = 'retail'` -> `retail_committed` at the line's own fulfilment warehouse.
* `demand_class = 'project'` with `demand_origin = 'scm_order_inquiry'` (the legacy sheet
  leg) -> `project_committed`, but ONLY while the SO has no active
  `projects.so_supply_decisions` row (section 4). Once CS confirms a decision, the sheet
  leg stops counting and the confirmed Buy residual - read from
  `projects.order_inquiry_rows` through `core_sales_order_line_id` - counts instead, once
  (AC-E04).
* A fifth column, `project_confirmed_committed`, carries the CONFIRMED leg ALONE.
  `project_committed` stays the sum of both legs because plan 6.4 says the Project column
  reads both, but only the confirmed leg is FIRM: AC-E04 defines Project need as "confirmed
  unplaced Buy" and AC-E05 bypasses the reorder trigger for "confirmed unplaced Project
  Buy". The sheet leg is a project-class demand READING that ordinary netting is supposed
  to see (S13b: "the book supplies the rest"), so the engine reads its firm figure off this
  column and leaves the sheet remainder inside the netted basis.
* `demand_class IS NULL` -> `unclassified_committed`.
* `demand_class = 'project'` WITHOUT the sheet origin and without an active decision is set
  aside today (PLAN_DEMAND_ORDER_SQL): it must stay out of all three columns, not just the
  old `committed` one.

Every test installs the CURRENT `app.services.scm.demand.COMMITTED_V_SQL` under a private
schema, exactly like `test_demand_reads_the_decision.py` - never `scm.committed_v` itself,
which would replace the real view for every other session on the shared local database for
the duration of the transaction. Querying the new column names against the CURRENT body is
the red: it does not select them yet, so Postgres raises `UndefinedColumn`. Once
`COMMITTED_V_SQL` is rewritten to select them (and, for the confirmed-Buy tests, to join
`projects.so_supply_decisions` / `projects.order_inquiry_rows` per PLAN section 4), the same
seeded data proves the right number lands in the right column - there is no string-matching
of the SQL anywhere in this file, only the view's own result.

Postgres, marker-prefixed seeding, rolled back at teardown. Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.demand import COMMITTED_V_SQL
from app.services.scm import reorder_run_service as run_svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import _link, _mk_product, _mk_stock, _mk_supplier, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTCHRM"

# See test_demand_reads_the_decision.py for why this is a PRIVATE schema name rather than
# `scm.committed_v` itself, and why it is fine to fix the name at import time: the schema is
# created and dropped inside each test's own rolled-back transaction, never shared live.
_SCHEMA = f"zzt_chrm_{uuid.uuid4().hex[:8]}"
VIEW_SQL = COMMITTED_V_SQL.replace("scm.committed_v", f"{_SCHEMA}.committed_v")


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        s.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))
        s.execute(text(VIEW_SQL))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    own = Warehouse(
        id=_u(), warehouse_code=_code("OWN")[:30], warehouse_name="own",
        is_active=True, counts_as_available=True,
    )
    brw = Warehouse(
        id=_u(), warehouse_code=_code("BRW")[:30], warehouse_name="brw pool",
        is_active=True, counts_as_available=True,
    )
    db.add_all([product, own, brw])
    db.flush()
    return {"product": product, "own": own, "brw": brw}


def _core_so_line(db, *, product_id, warehouse_id, qty=10, delivered=0, demand_class=None,
                  demand_origin=None, status="open", line_status="open"):
    """One core `public.sales_order_lines` row with its own header. Reusable by the
    view-level tests (`world`-shaped) and the recommendation-snapshot tests, which only
    have bare ids off `tests.scm.test_m3_run`'s raw-SQL builders."""
    so = SalesOrder(
        id=_u(), so_number=_code("SO"), status=status,
        demand_class=demand_class, demand_origin=demand_origin,
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product_id, warehouse_id=warehouse_id,
        qty_ordered=qty, qty_delivered=delivered, line_status=line_status,
        required_date=_today() + timedelta(days=14),
    )
    db.add(line)
    db.flush()
    return so, line


def _line(db, world, *, warehouse=None, qty=10, delivered=0, demand_class=None,
          demand_origin=None, status="open", line_status="open") -> SalesOrderLine:
    wh = warehouse or world["own"]
    return _core_so_line(
        db, product_id=world["product"].id, warehouse_id=wh.id, qty=qty,
        delivered=delivered, demand_class=demand_class, demand_origin=demand_origin,
        status=status, line_status=line_status,
    )


#: A (product, warehouse) with nothing counted has NO row, and must not grow one.
#: `scm.committed_v` is a GROUP BY over the lines that count, so a set-aside project
#: order, a superseded decision or a location the product was never ordered at simply
#: produces no group - which is today's behaviour and exactly what AC-F07 pins when it
#: says the view's "cardinality and join keys remain unchanged". Emitting a zero row per
#: (product, warehouse) instead would add keys to `scm.net_position_v`, and every one of
#: them would enter planning as a SKU with net 0. So absence READS as zero here rather
#: than being asserted into existence; `.one()` would have tested the opposite rule.
_EMPTY = {"committed": 0, "project_committed": 0, "project_confirmed_committed": 0,
          "retail_committed": 0, "unclassified_committed": 0}


def _row(db, world, warehouse=None) -> dict:
    wh = warehouse or world["own"]
    row = db.execute(
        text(
            f"SELECT committed, project_committed, project_confirmed_committed, "
            f"retail_committed, unclassified_committed "
            f"FROM {_SCHEMA}.committed_v "
            f"WHERE product_id = :p AND warehouse_id = :w"
        ),
        {"p": str(world["product"].id), "w": str(wh.id)},
    ).mappings().one_or_none()
    return dict(row) if row is not None else dict(_EMPTY)


# --------------------------------------------------------------------------- #
# the three new columns, on one row (AC-F07, 6.4)
# --------------------------------------------------------------------------- #

def test_committed_v_gains_three_channel_columns_summing_to_committed(db, world):
    """One row per (product, warehouse) still - `.one()` fails if channel split it in two."""
    _line(db, world, qty=30, demand_class="retail")
    _line(db, world, qty=20, demand_class="project", demand_origin="scm_order_inquiry")
    _line(db, world, qty=5, demand_class=None)

    row = _row(db, world)

    assert row["retail_committed"] == 30
    assert row["project_committed"] == 20
    assert row["unclassified_committed"] == 5
    assert row["committed"] == 55 == (
        row["project_committed"] + row["retail_committed"] + row["unclassified_committed"]
    )
    # `committed` is still the sum of exactly THOSE three. The confirmed column is a
    # subset of `project_committed`, never a fourth addend - adding it would count the
    # confirmed Buy twice.
    assert row["project_confirmed_committed"] == 0, (
        "the sheet leg is not confirmed Buy: nothing here points at an active decision"
    )


def test_retail_class_line_lands_in_retail_committed_at_its_own_warehouse(db, world):
    """AC-E01: the persisted class, not the location, decides the column."""
    _line(db, world, qty=12, demand_class="retail")

    row = _row(db, world)

    assert row["retail_committed"] == 12
    assert row["project_committed"] == 0
    assert row["unclassified_committed"] == 0


def test_project_class_with_sheet_origin_lands_in_project_committed(db, world):
    """The legacy sheet leg (AC-E04): `demand_origin='scm_order_inquiry'` is what makes an
    unconfirmed project-class line count at all."""
    _line(db, world, qty=18, demand_class="project", demand_origin="scm_order_inquiry")

    row = _row(db, world)

    assert row["project_committed"] == 18
    # ... and it is NOT firm. The sheet leg is read as project-class demand and netted
    # like any other commitment (S13b); only the confirmed leg bypasses the trigger.
    assert row["project_confirmed_committed"] == 0
    assert row["retail_committed"] == 0
    assert row["unclassified_committed"] == 0


def test_null_demand_class_lands_in_unclassified_committed(db, world):
    """AC-E02: a missing class is an exception, never folded into retail or dropped."""
    _line(db, world, qty=9, demand_class=None)

    row = _row(db, world)

    assert row["unclassified_committed"] == 9
    assert row["project_committed"] == 0
    assert row["retail_committed"] == 0


def test_project_class_fulfilled_from_brw_stays_project(db, world):
    """AC-E02: location never classifies demand. Fulfilled from the BRW-coded warehouse,
    the persisted class still wins - it is not reclassified retail because of where it is
    filled, and it is not double counted at the OWN warehouse either."""
    _line(db, world, warehouse=world["brw"], qty=14,
          demand_class="project", demand_origin="scm_order_inquiry")

    brw_row = _row(db, world, warehouse=world["brw"])
    own_row = _row(db, world, warehouse=world["own"])

    assert brw_row["project_committed"] == 14
    assert brw_row["retail_committed"] == 0
    assert own_row["committed"] == 0


def test_project_class_without_sheet_origin_or_decision_is_set_aside(db, world):
    """Unchanged existing behaviour (PLAN_DEMAND_ORDER_SQL), now proven on all three
    columns: a project-class SO that came in through the normal book (no sheet origin) and
    has no confirmed CS decision contributes to NOTHING yet - not `committed`, and not any
    of the three new columns either."""
    _line(db, world, qty=40, demand_class="project", demand_origin=None)

    row = _row(db, world)

    assert row["committed"] == 0
    assert row["project_committed"] == 0
    assert row["project_confirmed_committed"] == 0
    assert row["retail_committed"] == 0
    assert row["unclassified_committed"] == 0


# --------------------------------------------------------------------------- #
# the confirmed Buy leg (AC-E04, section 4, `projects.so_supply_decisions`)
# --------------------------------------------------------------------------- #

def _confirmed_leg(db, *, product_id, warehouse_id, buy_qty, decision_state="active",
                    inquiry_state=None, core_line=None):
    """The full section-4 chain: a Project SO whose core SO line is reconciled, with one
    Buy-verb Order Inquiry row pointing at an `active` `SOSupplyDecision`.

    `SOSupplyDecision` and `OrderInquiryRow.supply_decision_id` are new (STAGE2-...
    worknotes section 0.1) - this helper's construction of them is exactly what makes every
    caller fail with an ImportError / TypeError until the coder adds them, which is the red
    this whole confirmed-leg half of the file is pinning.
    """
    from app.models.project_so import (  # noqa: PLC0415 - deliberately deferred, see docstring
        IV_ORDER,
        INQUIRY_RAISED,
        OrderInquiry,
        OrderInquiryRow,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
        SOSupplyDecision,
    )
    from app.services.project_service import register_project
    from app.models.user import User
    from tests.scm.conftest import SORENTO_COMPANY_ID

    if core_line is None:
        so, core_line = _core_so_line(
            db, product_id=product_id, warehouse_id=warehouse_id, qty=buy_qty,
            demand_class="project", demand_origin=None,
        )

    owner_id = _u()
    db.add(User(id=owner_id, email=f"{owner_id}@{MARKER.lower()}.test", name=f"{MARKER} CS"))
    db.flush()
    project = register_project(
        db, company_id=SORENTO_COMPANY_ID, actor_user_id=owner_id,
        developer_party_id=None, title=f"{MARKER} project {_u()[:8]}",
    )
    pso = ProjectSalesOrder(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_id=project.id,
        provisional_ref=_code("PSO"), so_id=core_line.sales_order_id,
    )
    db.add(pso)
    db.flush()
    pso_line = ProjectSalesOrderLine(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
        line_no=1, product_id=product_id, qty=buy_qty,
        core_sales_order_line_id=core_line.id,
    )
    db.add(pso_line)
    db.flush()
    inquiry = OrderInquiry(id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id)
    db.add(inquiry)
    db.flush()
    decision = SOSupplyDecision(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
        revision_no=1, state=decision_state,
    )
    db.add(decision)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), company_id=SORENTO_COMPANY_ID, order_inquiry_id=inquiry.id,
        so_line_id=pso_line.id, qty=buy_qty, verb=IV_ORDER,
        state=inquiry_state or INQUIRY_RAISED, supply_decision_id=decision.id,
    )
    db.add(row)
    db.flush()
    return {"pso": pso, "decision": decision, "inquiry_row": row, "core_line": core_line}


def test_confirmed_buy_reaches_project_committed_at_the_core_lines_location(db, world):
    """AC-E04 main case, and the proof that `PROJECT_BUY_SQL` / `project_buy_committed_sql`
    is what the view actually uses: nothing else in this test states the product's Buy is
    project demand except the view's own result."""
    _confirmed_leg(db, product_id=world["product"].id, warehouse_id=world["own"].id, buy_qty=8)

    row = _row(db, world)

    assert row["project_committed"] == 8
    assert row["project_confirmed_committed"] == 8, (
        "a Buy row pointing at an active decision is the firm leg"
    )
    assert row["retail_committed"] == 0
    assert row["unclassified_committed"] == 0


def test_a_superseded_decision_contributes_nothing(db, world):
    """AC-E04: only an `active` decision's Buy counts."""
    _confirmed_leg(db, product_id=world["product"].id, warehouse_id=world["own"].id,
                   buy_qty=8, decision_state="superseded")

    row = _row(db, world)

    assert row["project_committed"] == 0
    assert row["project_confirmed_committed"] == 0


def test_a_placed_or_actioned_inquiry_row_contributes_nothing(db, world):
    """AC-E04: "unconfirmed, ... and already placed quantity are excluded" - only the
    UNPLACED state counts as current confirmed unplaced Buy."""
    from app.models.project_so import INQUIRY_ACTIONED  # noqa: PLC0415

    _confirmed_leg(db, product_id=world["product"].id, warehouse_id=world["own"].id,
                   buy_qty=8, inquiry_state=INQUIRY_ACTIONED)

    row = _row(db, world)

    assert row["project_committed"] == 0
    assert row["project_confirmed_committed"] == 0


def test_confirmed_decision_and_sheet_origin_counts_the_confirmed_buy_once(db, world):
    """Section 4: "a sheet-named SO that CS later confirms counts once: the confirmed Buy
    replaces the sheet quantity." The core SO here carries BOTH the old sheet-origin stamp
    (qty 20) and a confirmed decision with a DIFFERENT Buy residual (qty 8) - the answer
    must be 8, never 20 and never 28.
    """
    so, core_line = _line(
        db, world, qty=20, demand_class="project", demand_origin="scm_order_inquiry",
    )
    _confirmed_leg(db, product_id=world["product"].id, warehouse_id=world["own"].id,
                   buy_qty=8, core_line=core_line)

    row = _row(db, world)

    assert row["project_committed"] == 8
    assert row["project_confirmed_committed"] == 8


def test_project_confirmed_committed_counts_only_the_confirmed_leg(db, world):
    """The two legs at ONE location, from two different orders, and the split between them.

    `project_committed` is the Project COLUMN and reads both legs (plan 6.4). Only the
    confirmed leg is firm (AC-E04, AC-E05), so `project_confirmed_committed` must exclude
    the sheet quantity entirely rather than merely rank behind it - the engine adds the
    confirmed figure past the reorder trigger, and a sheet quantity riding along there
    buys stock a shared pool already holds.
    """
    _line(db, world, qty=18, demand_class="project", demand_origin="scm_order_inquiry")
    _confirmed_leg(db, product_id=world["product"].id, warehouse_id=world["own"].id,
                   buy_qty=8)

    row = _row(db, world)

    assert row["project_committed"] == 26
    assert row["project_confirmed_committed"] == 8
    # Still one row, and `committed` still the sum of the three channel columns.
    assert row["committed"] == 26 == (
        row["project_committed"] + row["retail_committed"] + row["unclassified_committed"]
    )


# --------------------------------------------------------------------------- #
# recommendation inputs snapshot (AC-F05, AC-F07, AC-E05)
# --------------------------------------------------------------------------- #
#
# These two exercise the whole engine in-process, via `scm_app` + `create_run` /
# `run_reorder(..., enqueue=False)` - the same synchronous idiom `tests/scm/test_m3_run.py`
# and `tests/scm/test_reorder_level_run.py` use to avoid RQ. `scm_app` is a live, rolled-back
# Postgres session (see `tests/scm/conftest.py`), not the blank/scratch schema the rest of
# this file uses for the view - the engine reads `scm.net_position_v` / `scm.committed_v`
# for real, so it has to run against the real views.

def _core_line_for_run(db, product_id, warehouse_id, *, qty, demand_class, demand_origin=None):
    so, line = _core_so_line(
        db, product_id=product_id, warehouse_id=warehouse_id, qty=qty,
        demand_class=demand_class, demand_origin=demand_origin,
    )
    return so, line


def _recs(db, run_id, product_id, warehouse_id):
    return [
        dict(r) for r in db.execute(
            text(
                "SELECT rec_type, rounded_qty, inputs FROM scm.reorder_recommendation "
                "WHERE run_id = :r AND product_id = :p AND warehouse_id = :w"
            ),
            {"r": run_id, "p": product_id, "w": warehouse_id},
        ).mappings().all()
    ]


def test_recommendation_inputs_carry_the_channel_need_breakdown(scm_app):
    """AC-F05 / AC-F07: the frozen per-location snapshot must state its Project, Retail and
    unclassified need SEPARATELY, and the unclassified figure must stay out of the sized
    order quantity even though it is visible.
    """
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTCHRM-RUN-A")
    pid = _mk_product(db, "ZZTCHRM-RUN-A")
    _mk_stock(db, pid, wid, 0)
    _link(db, pid, _mk_supplier(db, "ZZTCHRM Run Supplier A"), moq=None, mult=None)
    _core_line_for_run(db, pid, wid, qty=30, demand_class="retail")
    _core_line_for_run(db, pid, wid, qty=7, demand_class=None)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=12)
    db.flush()

    created = run_svc.create_run(db, ["ZZTCHRM-RUN-A"], "warehouse", enqueue=False)
    run_svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid, wid)
    assert rows, "a firm project buy plus outstanding retail demand must trigger a buy"
    inputs = rows[0]["inputs"]
    assert inputs["project_need"] == 12
    assert inputs["retail_need"] == 30
    assert inputs["unclassified_need"] == 7
    # Unclassified is visible but never sized into the order (AC-E06 at the location level).
    assert float(rows[0]["rounded_qty"] or 0) == 42.0


def test_project_need_bypasses_net_position_subtraction(scm_app):
    """AC-E05, worked exactly as the plan states it: a firm project buy of 5, with on-hand
    100 sitting far above it, must still read as project need 5 - and, because nothing else
    is short, must still produce a recommendation at all. Under the OLD net-position-only
    engine this location would never trigger a buy in the first place.
    """
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTCHRM-RUN-B")
    pid = _mk_product(db, "ZZTCHRM-RUN-B")
    _mk_stock(db, pid, wid, 100)
    _link(db, pid, _mk_supplier(db, "ZZTCHRM Run Supplier B"), moq=None, mult=None)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=5)
    db.flush()

    created = run_svc.create_run(db, ["ZZTCHRM-RUN-B"], "warehouse", enqueue=False)
    run_svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid, wid)
    assert rows, "firm project need must trigger a buy even though on-hand covers it"
    assert rows[0]["inputs"]["project_need"] == 5
    assert float(rows[0]["rounded_qty"] or 0) >= 5.0


def test_sheet_leg_project_demand_is_netted_and_buys_nothing_when_stock_covers_it(scm_app):
    """The ruling this column exists for (plan 5.3 / AC-E04 / AC-E05, S13b).

    A sheet-origin project SO - `demand_origin = 'scm_order_inquiry'` with NO confirmed CS
    decision - is a project-class demand READING, not firm Buy. 20 demanded against 100 on
    hand is covered, so nothing may be bought: the sheet quantity stays inside the netted
    basis exactly as it did before the channel split, and `project_need` (the figure that
    bypasses the trigger) is 0.

    This is the small-scale form of `test_pool_netting_parity.
    test_a_shared_pool_covers_its_bins_so_nothing_is_bought`, which is the same rule with a
    shared pool doing the covering.
    """
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTCHRM-RUN-C")
    pid = _mk_product(db, "ZZTCHRM-RUN-C")
    _mk_stock(db, pid, wid, 100)
    _link(db, pid, _mk_supplier(db, "ZZTCHRM Run Supplier C"), moq=None, mult=None)
    _core_line_for_run(db, pid, wid, qty=20, demand_class="project",
                       demand_origin="scm_order_inquiry")
    db.flush()

    created = run_svc.create_run(db, ["ZZTCHRM-RUN-C"], "warehouse", enqueue=False)
    run_svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid, wid)
    assert [r["rec_type"] for r in rows] == ["covered"], (
        "stock covers the sheet leg, so the engine may only SUGGEST using it - a buy here "
        "means unconfirmed project-class demand was treated as firm"
    )
    inputs = rows[0]["inputs"]
    assert inputs["project_need"] == 0, "nothing is confirmed, so nothing is firm"
    assert inputs["project_sheet_need"] == 20, (
        "the sheet quantity is still stated on the frozen row - it is netted, not dropped"
    )
    # Netted like any other commitment: 100 on hand less 20 committed, which is what the
    # engine saw before the channel split existed.
    assert inputs["retail_net"] == 80
