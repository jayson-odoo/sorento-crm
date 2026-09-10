"""PLAN-po-spo-site-pool-and-order-sheet-downloads.md - S1/S2/S3, test-first.

The one rule under test: a warehouse counts toward a product's SPO/PO figures only when
it is an ACTIVE SITE POOL (`app.services.scm.pool_predicate.active_site_pool_sql`) - active
and not `segment='project'`. A project bin's SPO/PO belongs to its own Order Inquiry and must
never reach a product-grain cell's `incoming_spo`/`outstanding_po`, the SPO/PO modal, the PO
book, the purchase-trend drill or the Net drill (`explain_net`) - and it must be product-WIDE
(every active site-pool warehouse the product has supply at), not narrowed to whatever
locations happen to be in the run's own warehouse scope (AC-3).

Every reference to a still-broken read (`_planning_rows`'s unfiltered `np.on_order` /
`po.ordered`, `spo_history_for_product`'s pool-id resolution, `po_book_service`'s bare
warehouse pairing, `purchase_trend_service`'s whole-product default) is deliberate: it is
what makes each test fail for "the site-pool gate does not exist yet" (a wrong number, or a
missing dict key) rather than a fixture bug.

S1 (AC-1..AC-6) drives the REAL engine (`svc.create_run` / `svc.run_reorder`) inside the
`scm_app` savepoint, the same harness `tests/scm/test_reorder_per_product.py` and
`tests/scm/test_pool_netting_parity.py` use - a site-pool gate inside `_planning_rows`' own
SQL cannot be proven any other way. S2 (AC-7..AC-10) and S3 (AC-13) call the read-only
service functions directly against hand-seeded rows, the `pg_session` idiom
`tests/scm/test_summary_order_service.py` and `test_order_summary_supply_docs.py` use.

Postgres only, marker-prefixed seeding, nothing borrowed with LIMIT 1 - CI's database is
empty.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.scm import po_book_service
from app.services.scm import purchase_trend_service
from app.services.scm import reorder_run_service as rrs
from app.services.scm import spo_supply
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.scm.test_reorder_level_run import _use_level_basis
from tests.scm.test_reorder_per_product import _open_po, _set_level

pytestmark = requires_pg

MARKER = "ZZTSPP"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =========================================================================== #
# S1 helpers - real engine, `scm_app` savepoint
# =========================================================================== #

def _pool(db) -> tuple[str, str, str, str]:
    """(head_id, head_code, bin_id, bin_code): a SITE POOL head (unclassified segment,
    which the rule reads as 'dealer') and its own PROJECT bin, the exact shape BRW /
    BRW-BB carries on the prod copy."""
    head_code = _code("HEAD")
    head = _mk_warehouse(db, head_code)
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :h WHERE id = :h"), {"h": head})
    bin_code = _code("BIN")
    bin_ = _mk_warehouse(db, bin_code, pool_warehouse_id=head, segment="project")
    return head, head_code, bin_, bin_code


def _shipment(db) -> InboundShipment:
    ship = InboundShipment(
        id=_u(), shipment_number=_code("SH")[:50], shipment_date=date.today(),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    return ship


def _spo(db, pid: str, wid: str, qty: float, *, received: float = 0.0) -> None:
    """One open SPO allocation, still to come - the ONLY shape `scm.on_order_v` (which
    `_planning_rows` reads as `np.on_order`) counts: an SPO with a booked, not-yet-landed
    shipment (migration 337)."""
    ship = _shipment(db)
    db.add(SPOAllocation(
        id=_u(), spo_number=_code("SPO")[:50], product_id=pid, warehouse_id=wid,
        inbound_shipment_id=ship.id, allocated_quantity=qty, quantity_received=received,
        receipt_status="pending", line_status="open",
    ))
    db.flush()


def _retail_committed(db, pid: str, wid: str, qty: float) -> None:
    from app.models.order import Customer, SalesOrder, SalesOrderLine

    cust = Customer(id=_u(), customer_code=_code("CUST"), customer_name="Test buyer")
    db.add(cust)
    db.flush()
    so = SalesOrder(id=_u(), so_number=_code("SO"), status="open", customer_id=cust.id,
                    demand_class="retail")
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=pid, warehouse_id=wid,
        qty_ordered=qty, qty_delivered=0, line_status="open",
    ))
    db.flush()


def _plan(db, warehouse_codes: list[str], product_code: str) -> str:
    created = rrs.create_run(db, warehouse_codes, enqueue=False, product_codes=[product_code])
    rrs.run_reorder(created["run_id"], db=db)
    return created["run_id"]


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT id, rec_type, warehouse_id::text AS warehouse_id, rounded_qty, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


def _product_row(rows: list[dict]) -> dict:
    prow = [r for r in rows if r["warehouse_id"] is None]
    assert len(prow) == 1, f"expected exactly one product-grain row, got {rows}"
    return prow[0]


def _seed_product(db, *, stem: str = "P") -> tuple[str, str]:
    code = _code(stem)
    pid = _mk_product(db, code)
    _link(db, pid, _mk_supplier(db, f"{code} supplier"))
    return pid, code


# =========================================================================== #
# AC-1 / AC-2 / AC-3: the product-grain cell, product-wide, site-pool only
# =========================================================================== #

def test_product_grain_spo_cell_counts_site_pool_only(scm_app):
    """AC-1: 96 still-to-come at a project bin, 40 at the site pool - the product-grain
    row's incoming_spo (frozen ``inputs.on_order``) is 40, not 136."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    head, head_code, bin_, bin_code = _pool(db)
    pid, code = _seed_product(db)
    _set_level(db, pid, None, 100000)
    _mk_stock(db, pid, head, 0)
    _mk_stock(db, pid, bin_, 0)
    _spo(db, pid, bin_, 96)
    _spo(db, pid, head, 40)

    run_id = _plan(db, [head_code, bin_code], code)
    row = _product_row(_recs(db, run_id, pid))

    assert float(row["inputs"]["on_order"]) == 40.0, (
        f"the project bin's SPO reached the product-grain cell: {row['inputs']}"
    )


def test_product_grain_po_cell_counts_site_pool_only(scm_app):
    """AC-2: 400 open PO at a project bin, 42 at the site pool - outstanding_po is 42."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    head, head_code, bin_, bin_code = _pool(db)
    pid, code = _seed_product(db)
    _set_level(db, pid, None, 100000)
    _mk_stock(db, pid, head, 0)
    _mk_stock(db, pid, bin_, 0)
    _open_po(db, pid, bin_, 400)
    _open_po(db, pid, head, 42)

    run_id = _plan(db, [head_code, bin_code], code)
    row = _product_row(_recs(db, run_id, pid))

    assert float(row["inputs"]["po_ordered"]) == 42.0, (
        f"the project bin's PO reached the product-grain cell: {row['inputs']}"
    )


def test_po_only_site_pool_warehouse_still_counts(scm_app):
    """AC-3: a site-pool warehouse (BRW-shaped) with NO stock row, no SPO and no
    committed SO - only an open PO line - must still reach the product-grain
    outstanding_po. Today `scm.net_position_v`'s ``keys`` CTE is
    ``stock UNION on_order_v UNION committed_v`` (migration 376) - it does not include
    ``po_ordered_v``, so a PO-only warehouse never becomes an ``np`` row at all and its PO
    is silently absent regardless of the site-pool gate."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    w1_code = _code("W1")
    w1 = _mk_warehouse(db, w1_code)
    brw_code = _code("BRW")
    brw = _mk_warehouse(db, brw_code)
    pid, code = _seed_product(db)
    _set_level(db, pid, None, 100000)
    _mk_stock(db, pid, w1, 0)  # gives W1 a net_position_v key; BRW gets none via stock
    _open_po(db, pid, brw, 400)  # BRW's ONLY presence in the whole plan

    run_id = _plan(db, [w1_code, brw_code], code)
    row = _product_row(_recs(db, run_id, pid))

    assert float(row["inputs"]["po_ordered"]) == 400.0, (
        f"a PO-only site-pool warehouse was dropped from the product-wide read: "
        f"{row['inputs']}"
    )


# =========================================================================== #
# AC-4: the netting follows - a bin SPO no longer covers a retail need
# =========================================================================== #

def test_bin_spo_no_longer_covers_a_retail_need(scm_app):
    """AC-4. Product A: 500 SPO at the project bin, retail committed 100 at the site
    pool, 0 on hand, level 0 - today the bin's SPO nets the shortfall to +400 and the
    plan reads 'covered'; the fix must trigger a Buy (net crosses zero the other way).
    Product B: the SAME 500 SPO at the site pool instead - already, and must stay,
    covered (non-regression)."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    head, head_code, bin_, bin_code = _pool(db)

    pid_a, code_a = _seed_product(db, stem="PA")
    _set_level(db, pid_a, None, 0)
    _mk_stock(db, pid_a, head, 0)
    _mk_stock(db, pid_a, bin_, 0)
    _spo(db, pid_a, bin_, 500)
    _retail_committed(db, pid_a, head, 100)

    pid_b, code_b = _seed_product(db, stem="PB")
    _set_level(db, pid_b, None, 0)
    _mk_stock(db, pid_b, head, 0)
    _mk_stock(db, pid_b, bin_, 0)
    _spo(db, pid_b, head, 500)
    _retail_committed(db, pid_b, head, 100)

    created = rrs.create_run(db, [head_code, bin_code], enqueue=False,
                             product_codes=[code_a, code_b])
    rrs.run_reorder(created["run_id"], db=db)
    run_id = created["run_id"]

    row_a = _product_row(_recs(db, run_id, pid_a))
    row_b = _product_row(_recs(db, run_id, pid_b))

    assert row_a["rec_type"] == "buy", (
        f"the bin's 500 SPO still covered a retail need it must not reach: {row_a}"
    )
    assert row_b["rec_type"] == "covered", (
        f"the SAME 500 SPO at the site pool must still cover: {row_b}"
    )


# =========================================================================== #
# AC-5: a location-grain row at the bin reads zero, at the head reads its own
# =========================================================================== #

def test_location_grain_row_at_a_bin_reads_zero_supply(scm_app):
    _, db, _, _ = scm_app
    # The shared lane database is a prod copy whose GLOBAL policy is already
    # `reorder_level` (see `test_pool_netting_parity.py`'s own note on this) - this AC is
    # about the LOCATION-grain path (`_emit_cell`), so the basis is pinned back to
    # `reorder_point` rather than trusting the ambient default.
    rrs.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET policy_type = 'reorder_point'"))
    head, head_code, bin_, bin_code = _pool(db)
    pid, code = _seed_product(db)
    _mk_stock(db, pid, head, 0)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, head, 1.0)
    _mk_demand(db, pid, bin_, 1.0)
    # A location with no committed demand of its own emits nothing at all (`_emit_cell`'s
    # `_covered_rec` early-return) - one unit at each location guarantees a row exists to
    # read the on_order/po_ordered figures off, whichever way the trigger falls.
    _retail_committed(db, pid, head, 1)
    _retail_committed(db, pid, bin_, 1)
    _spo(db, pid, head, 40)
    _spo(db, pid, bin_, 55)
    _open_po(db, pid, head, 20)
    _open_po(db, pid, bin_, 30)

    run_id = _plan(db, [head_code, bin_code], code)
    rows = _recs(db, run_id, pid)
    by_wh = {r["warehouse_id"]: r for r in rows}
    assert len(rows) == 2, f"expected one row per location, got {rows}"

    bin_row = by_wh[bin_]
    head_row = by_wh[head]
    assert float(bin_row["inputs"]["on_order"]) == 0.0, bin_row["inputs"]
    assert float(bin_row["inputs"]["po_ordered"]) == 0.0, bin_row["inputs"]
    assert float(head_row["inputs"]["on_order"]) == 40.0, head_row["inputs"]
    assert float(head_row["inputs"]["po_ordered"]) == 20.0, head_row["inputs"]


# =========================================================================== #
# AC-6: the Net drill sums the same site-pool scope
# =========================================================================== #

def test_explain_net_legs_sum_to_net_with_bin_spo_present(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    head, head_code, bin_, bin_code = _pool(db)
    pid, code = _seed_product(db)
    _set_level(db, pid, None, 0)
    _mk_stock(db, pid, head, 0)
    _mk_stock(db, pid, bin_, 0)
    _spo(db, pid, bin_, 500)
    _retail_committed(db, pid, head, 100)

    run_id = _plan(db, [head_code, bin_code], code)
    row = _product_row(_recs(db, run_id, pid))

    breakdown = rrs.explain_net(db, row["id"])
    assert breakdown["on_order"] == 0.0, (
        f"the bin's SPO reached the product-grain net drill: {breakdown}"
    )
    assert breakdown["committed"] == 100.0
    assert breakdown["on_hand"] == 0.0
    assert breakdown["net"] == (
        breakdown["on_hand"] + breakdown["on_order"] + breakdown["po_ordered"]
        - breakdown["committed"]
    )
    assert breakdown["net"] == -100.0, breakdown


# =========================================================================== #
# S2 - the two modals + the PO book + purchase-trend read what the cell summed
# =========================================================================== #

@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _cat_uom(db) -> tuple[ProductCategory, UnitOfMeasure]:
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=_code("uom"))
    db.add_all([cat, uom])
    db.flush()
    return cat, uom


def _product2(db, cat, uom, *, stem: str = "SKU") -> Product:
    p = Product(
        id=_u(), product_code=_code(stem), product_name=_code(stem),
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p)
    db.flush()
    return p

def _pool2(db) -> tuple[Warehouse, Warehouse]:
    head = Warehouse(id=_u(), warehouse_code=_code("HEAD")[:30], warehouse_name="head",
                     is_active=True)
    db.add(head)
    db.flush()
    head.pool_warehouse_id = head.id
    db.add(head)
    db.flush()
    bin_ = Warehouse(id=_u(), warehouse_code=_code("BIN")[:30], warehouse_name="bin",
                     is_active=True, pool_warehouse_id=head.id, segment="project")
    db.add(bin_)
    db.flush()
    return head, bin_


def _shipment2(db) -> InboundShipment:
    ship = InboundShipment(
        id=_u(), shipment_number=_code("SH")[:50], shipment_date=date.today(),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    return ship


def _spo2(db, product, wh, qty, *, received: float = 0.0, spo_number: str | None = None):
    ship = _shipment2(db)
    row = SPOAllocation(
        id=_u(), spo_number=spo_number or _code("SPO")[:50], product_id=product.id,
        warehouse_id=(wh.id if wh else None), inbound_shipment_id=ship.id,
        allocated_quantity=qty, quantity_received=received, receipt_status="pending",
        line_status="open",
    )
    db.add(row)
    db.flush()
    return row


def _recent_issue_date() -> date:
    """Safely inside `purchase_trend_service`'s 'recent' window: the trend excludes the
    month the run sits in (a partial month compared against whole ones), so `date.today()`
    itself is EXCLUDED - a PO must be dated before the start of this month."""
    return date.today().replace(day=1) - timedelta(days=10)


def _po2(db, product, wh, *, po_number: str | None = None, qty_ordered: float,
        qty_received: float = 0.0, status: str = "active", issue_date=None):
    po = PurchaseOrder(id=_u(), po_number=po_number or _code("PO")[:50], status=status,
                       issue_date=issue_date or _recent_issue_date())
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=(wh.id if wh else None), qty_ordered=qty_ordered,
        qty_received=qty_received, line_status="open",
    )
    db.add(line)
    db.flush()
    return po, line


def _run2(db) -> ReorderRun:
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()
    return run


# --- AC-7 / AC-8: the SPO modal ------------------------------------------------------

def test_spo_history_open_rows_sum_to_the_cell(db):
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    keep = f"{MARKER}-KEEP-{_u()[:8]}"[:50]
    drop = f"{MARKER}-DROP-{_u()[:8]}"[:50]
    _spo2(db, product, head, 40, spo_number=keep)
    _spo2(db, product, bin_, 96, spo_number=drop)

    result = spo_supply.spo_history_for_product(db, run.id, product.id)
    open_rows = result["open"]
    total = sum(r["qty"] - r["received_qty"] for r in open_rows)
    assert total == 40.0, f"the bin's SPO reached the row's SPO cell: {open_rows}"
    numbers = {r["spo_number"] for r in open_rows}
    assert drop not in numbers, open_rows


def test_spo_history_history_tab_is_site_pool_only(db):
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    keep = f"{MARKER}-HEADHIST-{_u()[:8]}"[:50]
    drop = f"{MARKER}-BINHIST-{_u()[:8]}"[:50]
    _spo2(db, product, head, 40, received=40, spo_number=keep)
    _spo2(db, product, bin_, 96, received=96, spo_number=drop)

    result = spo_supply.spo_history_for_product(db, run.id, product.id)
    numbers = {r["spo_number"] for r in result["history"]}
    assert keep in numbers, result["history"]
    assert drop not in numbers, result["history"]


# --- AC-9: the PO book ---------------------------------------------------------------

def test_po_book_serves_the_product_grain_key_with_site_pool_lines(db):
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=None, rounded_qty=1, status="proposed",
    ))
    db.flush()
    _po2(db, product, head, qty_ordered=42)
    _po2(db, product, bin_, qty_ordered=400)

    book = po_book_service.po_book_for_run(db, run.id)["po_book"]
    key = f"{product.id}:"
    assert key in book, f"the product-grain key must carry the site-pool line: {book.keys()}"
    remaining = sum(l["remaining"] for l in book[key])
    assert remaining == 42.0, f"the bin's PO reached the product-grain key: {book[key]}"


def test_po_book_keeps_p8_project_only_exclusion(db):
    """Non-regression: a cell whose demand is entirely project-class still serves no
    receipts at all (P8)."""
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=head.id, rounded_qty=1, status="proposed",
        inputs={"project_committed": 10, "retail_committed": 0},
    ))
    db.flush()
    _po2(db, product, head, qty_ordered=42)

    book = po_book_service.po_book_for_run(db, run.id)["po_book"]
    key = f"{product.id}:{head.id}"
    assert key not in book, "a project-only cell must serve no receipts (P8)"


def test_po_book_location_row_at_a_bin_serves_nothing(db):
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=bin_.id, rounded_qty=1, status="proposed",
    ))
    db.flush()
    _po2(db, product, bin_, qty_ordered=30)

    book = po_book_service.po_book_for_run(db, run.id)["po_book"]
    key = f"{product.id}:{bin_.id}"
    assert key not in book, f"a location row AT a project bin must serve nothing: {book}"


# --- AC-10: purchase-trend -----------------------------------------------------------

def test_purchase_trend_without_warehouse_reads_site_pool(db):
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=None, rounded_qty=1, status="proposed",
    ))
    db.flush()
    _po2(db, product, head, qty_ordered=42, qty_received=42, status="closed")
    _po2(db, product, bin_, qty_ordered=96, qty_received=96, status="closed")

    result = purchase_trend_service.purchase_trend_for_run(db, run.id, warehouse_id=None)
    entry = result["products"][str(product.id)]
    assert entry["recent_qty"] == 42.0, (
        f"a bin purchase reached the product-wide (no-warehouse) trend: {entry}"
    )


def test_purchase_trend_with_warehouse_keeps_single_read(db):
    """Non-regression: naming one warehouse still narrows to it alone."""
    cat, uom = _cat_uom(db)
    product = _product2(db, cat, uom)
    head, bin_ = _pool2(db)
    run = _run2(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=None, rounded_qty=1, status="proposed",
    ))
    db.flush()
    _po2(db, product, head, qty_ordered=42, qty_received=42, status="closed")
    _po2(db, product, bin_, qty_ordered=96, qty_received=96, status="closed")

    result = purchase_trend_service.purchase_trend_for_run(db, run.id, warehouse_id=head.id)
    entry = result["products"][str(product.id)]
    assert entry["recent_qty"] == 42.0, entry


# =========================================================================== #
# S3 - AC-13: the sheet's frozen supply columns tally with the grid cells
# =========================================================================== #

def test_sheet_supply_columns_equal_the_grid_cells(scm_app):
    """The sheet's own read (`summary_order_service`) is already site-pool-scoped
    (S9/S14); the grid's read (`_planning_rows`) is not, yet. Today the two disagree -
    this pins that they must not."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    head, head_code, bin_, bin_code = _pool(db)
    pid, code = _seed_product(db)
    _set_level(db, pid, None, 100000)
    _mk_stock(db, pid, head, 0)
    _mk_stock(db, pid, bin_, 0)
    _spo(db, pid, bin_, 96)
    _spo(db, pid, head, 40)
    _open_po(db, pid, bin_, 400)
    _open_po(db, pid, head, 42)

    run_id = _plan(db, [head_code, bin_code], code)
    row = _product_row(_recs(db, run_id, pid))
    grid_spo = float(row["inputs"]["on_order"])
    grid_po = float(row["inputs"]["po_ordered"])

    from app.services.scm import summary_order_service as sos

    assert sos.write_rows(db, run_id) == 1
    report_row = sos.report(db, run_id=run_id)["rows"][0]

    assert float(report_row["incoming_spo_qty"]) == grid_spo == 40.0, (
        report_row["incoming_spo_qty"], grid_spo,
    )
    assert float(report_row["po_open_qty"]) == grid_po == 42.0, (
        report_row["po_open_qty"], grid_po,
    )
