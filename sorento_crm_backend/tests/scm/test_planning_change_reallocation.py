"""Slice D, reallocation (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`,
UAC AC-D1 to AC-D6, issue #859, scenarios S2/S3 in
`documentation/plans/scm/mockups/so-change-management-grill-v4.html`). RED before the
coder's slice lands.

Slice C already composes a correct `reallocate` component in `suggestion_json` (measured
directly below) - what this slice adds is the APPLY-time EXECUTION of it: taking the freed
quantity's link off the line's own row and re-dealing it (dealer pool / another raised row
/ the pool as a last resort for a PO-sourced freed qty; another order's reserve for a
reserve-sourced one). Every test below confirms the row and applies it; the composed
suggestion is asserted first (usually already correct, sometimes not - AC-D4 needs the
re-run to recognise a nearer unlinked rival, which it does not do today either), then the
apply-time redeal is asserted and is the actual red.

Fixtures, imported rather than copied:
- `tests.scm.test_planning_change_recompute_and_diff` (`_qty_down_with_po_world`,
  `_only_row`) - S2's own shape: 234 wholly Buy, 134 placed on a real PO, 100 raised
  unlinked, then dropped to 100 (AC-C4's own fixture, reused verbatim for D1-D3).
- `tests.scm.test_planning_change_delta_seam` (`_held_reserve_world`, `_seed_order`,
  `_change_and_batch`, `_only_row`, `NON_IMMEDIATE`) for AC-D4's reserve/S3 shape.
- `tests.test_planning_changes` (`api`, `_classification`, `_confirm`, `_diff_change`,
  `_core_so`, `_core_line`, `_project_so`, `_project_line`, `_line_payload`) - the same
  `(client, world)` convention every other Slice A-C file in this lane uses.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.outstanding_diff import CLOSED, DATE_MOVED, QTY_CHANGED, Change, Diff, Line

from tests._pg_fixture import blank_session
from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    BASE,
    api,
    _classification,
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _project_line,
    _project_so,
    _uid,
    _warehouse,
)
from tests.scm.test_planning_change_recompute_and_diff import (
    _only_row,
    _qty_down_with_po_world,
)
from tests.scm.test_planning_change_delta_seam import (
    _change_and_batch,
    _held_reserve_world,
    _hold_qty,
    _seed_order,
)
from tests.scm.test_planning_change_delta_seam import _only_row as _seam_only_row
from tests.scm.test_ladder_v7_supply_borrow import _spo
from app.schemas.project_supply import ConfirmLine, ConfirmReserveComponent, ConfirmSupplyBody

MARKER = "zzt-realloc"


def _confirm_row_and_apply(db, batch, actor):
    row = _only_row(db, batch)
    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), actor)
    db.commit()
    return row, result


def _drop_line_to_100(api):
    """S2's shape (AC-C4's own fixture, reused verbatim): 234 wholly Buy, 134 placed on a
    real PO, 100 raised unlinked - qty dropped to 100, freeing 34 of the placed PO."""
    world, core_so, core_line, order, line, po = _qty_down_with_po_world(api)
    db = world.db
    core_line.qty_ordered = Decimal("100")
    line.qty = Decimal("100")
    db.flush()
    changed = _diff_change(
        QTY_CHANGED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=date(2027, 3, 1), old_qty="234", new_qty="100",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    return world, core_so, core_line, order, line, po, batch


def _links_of(db, row_id) -> list:
    return db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()


def _wholly_placed_buy_world(api, *, qty="34", warehouse=None):
    """A single held Buy line, its WHOLE quantity placed on a real PO - no remainder, no
    other line of the order carrying this product. The removal shape rule 6 has to answer:
    a line's whole placement has to move somewhere when the line itself goes, never simply
    released for nothing (`_place_row_on_a_real_po`'s own shape, reused rather than copied
    for the qty-down world since this needs the WHOLE quantity placed, not a partial).

    `warehouse` defaults to `world.own_wh` (which carries a pool link) - passed explicitly
    as a no-pool warehouse for the "no pool configured" shape (R3)."""
    client, world = api
    db = world.db
    wh = warehouse or world.own_wh
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, wh, qty_ordered=qty,
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty=qty, buy_reason="ZZT no stock anywhere"),
    ]})
    raised_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=wh.id,
        qty_ordered=Decimal(qty), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        raised_row.id, [{"po_line_id": po_line.id, "qty": qty}], actor_user_id=world.actor,
    )
    db.commit()
    db.expire_all()
    raised_row = db.get(OrderInquiryRow, raised_row.id)
    assert raised_row.state == INQUIRY_PLACED, raised_row.state
    return world, core_so, core_line, order, line, po, po_line


def _cancel_the_line(db, world, core_so, core_line, *, location=None):
    """Write-first (the book removes the line), then a CLOSED Change fed to build_batch -
    the same shape `_so400884_shape`'s own "line 1 is removed - cancelled" save uses.

    `location` defaults to `world.own_wh`'s own code - passed explicitly when the line
    being cancelled sits at a different warehouse (R3's no-pool shape)."""
    loc = location or world.own_wh.warehouse_code
    old_qty = float(core_line.qty_ordered)
    core_line.line_status = "cancelled"
    db.flush()
    before = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                  location=loc, qty=old_qty,
                  required_date=core_line.required_date, row_ref=str(core_line.id))
    change = Change(CLOSED, core_so.so_number, world.product.product_code,
                     loc, before=before, after=None)
    batch = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change]),
        applied_line_ids={id(change): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="test.xlsx",
    )
    db.commit()
    return batch


def _two_lines_split_po_world(api, *, warehouse=None):
    """One order, two lines, same product. Line 1 = Buy 34, its WHOLE quantity placed
    across TWO real purchase-order lines of 17 each (`_document_links_by_row`'s own
    per-po-line split shape - one line's placement routinely sits on several purchase-
    order lines). Line 2 = Buy 17, held but left UNPLACED - the only same-order survivor,
    with exactly 17 of headroom, no more and no less: enough to take ONE of line 1's two
    links whole, nothing left over for the other."""
    client, world = api
    db = world.db
    wh = warehouse or world.own_wh
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, wh, qty_ordered="34",
                              required_date=date(2027, 3, 1))
    core_line_2 = _core_line(db, core_so, world.product, wh, qty_ordered="17",
                              required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    line_2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_line_2)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line_1.id, buy_qty="34", buy_reason="ZZT no stock anywhere"),
        _line_payload(line_2.id, buy_qty="17", buy_reason="ZZT no stock anywhere"),
    ]})
    row_1 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_1.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    row_2 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line_a = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=wh.id,
        qty_ordered=Decimal("17"), qty_received=Decimal("0"), line_status="open",
    )
    po_line_b = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=wh.id,
        qty_ordered=Decimal("17"), qty_received=Decimal("0"), line_status="open",
    )
    db.add_all([po_line_a, po_line_b])
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        row_1.id,
        [
            {"po_line_id": po_line_a.id, "qty": "17"},
            {"po_line_id": po_line_b.id, "qty": "17"},
        ],
        actor_user_id=world.actor,
    )
    db.commit()
    db.expire_all()
    row_1 = db.get(OrderInquiryRow, row_1.id)
    assert row_1.state == INQUIRY_PLACED, row_1.state
    return {
        "world": world, "core_so": core_so, "core_line_1": core_line_1,
        "core_line_2": core_line_2, "order": order, "line_1": line_1, "line_2": line_2,
        "po": po, "po_line_a": po_line_a, "po_line_b": po_line_b, "row_1": row_1,
        "row_2": row_2,
    }


# --------------------------------------------------------------------------- #
# AC-D1: freed PO qty goes to the dealer pool when the product is hot-selling
# --------------------------------------------------------------------------- #

def test_freed_po_qty_goes_to_the_dealer_pool_when_hot_selling(api):
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db
    # Dealer hot-selling at a counts_as_available warehouse (contract point 1a).
    _classification(db, world.product, world.own_wh, abc_class_retail="A")
    db.commit()

    # Another order's ORDER row, raised, unlinked - present but must NOT receive the
    # freed qty, since the product is dealer hot-selling (pool wins over relinking).
    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="50",
                                  required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(api[0], other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="50", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    # The line's own row: settled at 100, its PO link reduced to 100 (the existing
    # confirm-time link-reduction mechanism, NOT Slice D - measured to already work).
    own_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()
    own_links = _links_of(db, own_row.id)
    assert sum(Decimal(str(l.qty)) for l in own_links) == Decimal("100"), own_links

    # The freed 34 lands on a POOL-LOCATION row (contract point 1a): a new
    # OrderInquiryRow, so_line_id NULL, verb ORDER, stock_location the pool code, qty 34,
    # linked to the SAME PO line for 34.
    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    assert pool_rows[0].qty == Decimal("34"), pool_rows[0].qty
    pool_links = _links_of(db, pool_rows[0].id)
    assert sum(Decimal(str(l.qty)) for l in pool_links) == Decimal("34"), pool_links

    # The other order's row is UNTOUCHED - the pool won because the product is hot-selling.
    db.refresh(other_row)
    assert other_row.state != INQUIRY_CANCELLED
    assert _links_of(db, other_row.id) == []

    assert (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.redirected_to_pool.is_(True)).count()
        == 0
    )


# --------------------------------------------------------------------------- #
# AC-D2: freed PO qty links to the first raised order row when NOT hot-selling
# --------------------------------------------------------------------------- #

def test_freed_po_qty_links_to_the_first_raised_order_row_when_not_hot_selling(api):
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db
    client = api[0]

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="50",
                                  required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="50", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    other_decision_id_before = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == other_order.id,
                SOSupplyDecision.state == DECISION_ACTIVE)
        .one()
        .id
    )

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    other_row = db.get(OrderInquiryRow, other_row.id)
    links = _links_of(db, other_row.id)
    assert sum(Decimal(str(l.qty)) for l in links) == Decimal("34"), links
    assert other_row.state == "partly_linked", other_row.state
    assert other_row.note and f"Found: {po.po_number} 34" in other_row.note, other_row.note

    # No new revision was written for the receiving order (contract point 1b).
    other_decision_id_after = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == other_order.id,
                SOSupplyDecision.state == DECISION_ACTIVE)
        .one()
        .id
    )
    assert other_decision_id_after == other_decision_id_before

    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER)
        .all()
    )
    assert pool_rows == [], pool_rows


# --------------------------------------------------------------------------- #
# AC-D2b: freed qty follows the linking engine's own priority
# --------------------------------------------------------------------------- #

def test_freed_qty_follows_the_linking_engines_priority(api):
    """Two other raised, unlinked rows for the same product - the earlier-due one wins
    (`_rank_raised_rows`'s own tie-break, delivery_date then created_at, with no active
    priority policy weighting anything)."""
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db
    client = api[0]

    def _raise_other(due, qty):
        other_so = _core_so(db, world.company_id)
        other_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered=qty,
                                 required_date=due)
        other_order = _project_so(db, world.project, so_id=other_so.id,
                                   autocount_doc_no=other_so.so_number)
        other_line = _project_line(db, other_order, line_no=1, product=world.product,
                                    core_line=other_core)
        db.commit()
        _confirm(client, other_order.id, {"lines": [
            _line_payload(other_line.id, buy_qty=qty, buy_reason="Nothing free elsewhere."),
        ]})
        return (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == other_line.id, OrderInquiryRow.verb == IV_ORDER)
            .one()
        )

    later_row = _raise_other(date(2027, 4, 1), "50")
    earlier_row = _raise_other(date(2027, 3, 5), "50")

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    earlier_row = db.get(OrderInquiryRow, earlier_row.id)
    later_row = db.get(OrderInquiryRow, later_row.id)
    assert _links_of(db, earlier_row.id), "the earlier-due row should have been linked first"
    assert _links_of(db, later_row.id) == [], "the later-due row should get nothing"


# --------------------------------------------------------------------------- #
# AC-D3: freed PO qty nobody needs lands on a pool row and counts as cover
# --------------------------------------------------------------------------- #

def test_freed_po_qty_nobody_needs_lands_on_a_pool_row_and_counts_as_cover(api):
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    assert pool_rows[0].qty == Decimal("34")
    pool_links = _links_of(db, pool_rows[0].id)
    assert sum(Decimal(str(l.qty)) for l in pool_links) == Decimal("34"), pool_links

    # The PO line's linked total now reads 134 (100 kept + 34 reallocated to the pool) -
    # its own gap is 0. No dedicated `unallocated_quantity` reader exists for a
    # PO-line-to-order-inquiry-row link today (only `_unallocated_quantity` in
    # `incoming_stock_service.py`, which is the DIFFERENT shipment/SPO-to-warehouse
    # allocation gap) - summed directly off `OrderInquiryLink` instead, which is what
    # such a reader would compute.
    own_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()
    total_linked = sum(
        Decimal(str(l.qty))
        for r_id in (own_row.id, pool_rows[0].id)
        for l in _links_of(db, r_id)
    )
    assert total_linked == Decimal("134"), total_linked
    from app.models.procurement import PurchaseOrderLine

    po_line = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == po.id)
        .one()
    )
    assert po_line.qty_ordered - total_linked == Decimal("0")


def test_a_reallocation_failure_is_loud_and_leaves_no_orphan_pool_row(api, monkeypatch):
    """D1 (review round, blocker): a reallocation failure must be loud, never a silent
    wrong row. `_execute_reallocations` catches every exception per component and only
    logs it, so a refusal from `place_on_po_allocations` (AppException 409 - a race on
    the PO line, say) is swallowed today: `_pool_row_for` has already flushed the pool
    row before the refusing call, the order's savepoint still commits, and apply reports
    success while that pool row sits in the database claiming nothing - exactly the
    orphan AC-D1 exists to forbid."""
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db

    from app.services.error_handler import AppException
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    def _refuse(self, row_id, allocations, *, actor_user_id=None, auto_trigger=None):
        raise AppException(409, "ZZT another process already claimed this PO line")

    monkeypatch.setattr(ProjectOrderInquiryService, "place_on_po_allocations", _refuse)

    row = _only_row(db, batch)
    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()

    assert result["failed_orders"], (
        "the refusal must surface as a failed order, not a silent success: "
        f"{result}"
    )
    assert core_so.so_number not in (result["applied_orders"] or [])

    db.expire_all()
    orphans = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert orphans == [], orphans


# --------------------------------------------------------------------------- #
# AC-D4 (S3): a reserve moves to an earlier unlinked order row, and the line
# giving it up is re-sourced whole
# --------------------------------------------------------------------------- #

def test_reserve_moves_to_the_earlier_order_row_and_the_line_is_resourced_whole():
    today = date.today()
    a_required = today + timedelta(days=20)
    a_new = today + timedelta(days=45)  # inside the reserve window
    b_required = today + timedelta(days=30)  # earlier than A's new date

    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=a_required)
        order_b, line_b, core_so_b, core_line_b = _seed_order(
            db, world["company_id"], world["project"], world["product"], world["own"],
            qty="80", required_date=b_required,
        )
        ProjectSupplyService(db).confirm(
            order_b,
            ConfirmSupplyBody(lines=[ConfirmLine(
                project_line_id=line_b.id, buy_qty="80", buy_reason="ZZT no stock anywhere",
            )]),
            actor_user_id=world["actor"],
        )
        db.commit()
        b_row = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == line_b.id, OrderInquiryRow.verb == IV_ORDER)
            .one()
        )
        b_decision_id_before = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order_b.id,
                    SOSupplyDecision.state == DECISION_ACTIVE)
            .one()
            .id
        )

        # Write-first: production always writes the book before building the batch off it.
        batch = _change_and_batch(db, world, new_required_date=a_new)
        assert batch is not None
        row = _seam_only_row(db, batch)
        components = row.suggestion_json["components"]
        reallocate = next((c for c in components if c["action"] == "reallocate"), None)
        assert reallocate is not None, components
        assert reallocate["source"] == "reserve", reallocate
        assert reallocate["qty_now"] == "80", reallocate
        assert reallocate["target"] == f"{core_so_b.so_number} ORDER 80", reallocate

        planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
        result = planning_change_service.apply(db, str(batch.id), world["actor"])
        db.commit()
        assert result["failed_orders"] == [], result["failed_orders"]

        db.expire_all()
        b_decision_id_after = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order_b.id,
                    SOSupplyDecision.state == DECISION_ACTIVE)
            .one()
            .id
        )
        assert b_decision_id_after == b_decision_id_before

        allocation = (
            db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == line_b.id, SOLineAllocation.confirmed_at.isnot(None))
            .one()
        )
        assert allocation.qty == Decimal("80")
        assert str(allocation.warehouse_id) == str(world["own"].id)

        b_row = db.get(OrderInquiryRow, b_row.id)
        assert b_row.state == INQUIRY_CANCELLED, b_row.state
        assert b_row.note and "Found: reserve 80" in b_row.note, b_row.note

        # The engine's own hold predicate (project_supply_service.py:7696-7767, restated
        # by `_hold_qty`): a plain `confirmed_at IS NOT NULL` sum here double-counts the
        # superseded revision's own 134 alongside the new revision's 134 stock hold, so
        # it never reads as "the reserve moved away" no matter what actually happened.
        assert _hold_qty(db, world["line"].id) == Decimal("0")

        a_live_rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == world["line"].id,
                    OrderInquiryRow.verb == IV_ORDER, OrderInquiryRow.state != INQUIRY_CANCELLED)
            .all()
        )
        assert len(a_live_rows) == 1, [(r.state, str(r.qty)) for r in a_live_rows]
        assert a_live_rows[0].qty == Decimal("134")
        assert a_live_rows[0].delivery_date == a_new


def test_a_reallocated_reserve_survives_the_receiving_orders_next_confirm():
    """D3 (review round, blocker): the S3 shape (AC-D4's own world), one step further -
    order B, the RECEIVER of the reallocated reserve, gets re-confirmed afterwards (a
    planner touching an unrelated line on the same order, say). `_move_reserve` writes
    the reallocated hold with `decision_id` set to whatever decision is active on B AT
    THAT MOMENT - the shape `_hold_query` uses for a hold belonging to A SPECIFIC
    revision, meant to stop counting the moment that revision is superseded. But this
    hold was never decided by B's revision; it was handed to B by A's change. Tied to a
    revision id, it is one re-confirm away from a decision that superseded it, and would
    read gone. It must be `None`: the shape `_hold_query` reserves for a hold belonging
    to no revision, so it survives every future revision B ever gets."""
    today = date.today()
    a_required = today + timedelta(days=20)
    a_new = today + timedelta(days=45)  # inside the reserve window
    b_required = today + timedelta(days=30)  # earlier than A's new date

    with blank_session() as db:
        world = _held_reserve_world(db, qty="134", required_date=a_required)
        order_b, line_b, core_so_b, core_line_b = _seed_order(
            db, world["company_id"], world["project"], world["product"], world["own"],
            qty="80", required_date=b_required,
        )
        ProjectSupplyService(db).confirm(
            order_b,
            ConfirmSupplyBody(lines=[ConfirmLine(
                project_line_id=line_b.id, buy_qty="80", buy_reason="ZZT no stock anywhere",
            )]),
            actor_user_id=world["actor"],
        )
        db.commit()

        batch = _change_and_batch(db, world, new_required_date=a_new)
        row = _seam_only_row(db, batch)
        planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
        result = planning_change_service.apply(db, str(batch.id), world["actor"])
        db.commit()
        assert result["failed_orders"] == [], result["failed_orders"]

        db.expire_all()
        moved_allocation = (
            db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == line_b.id, SOLineAllocation.confirmed_at.isnot(None))
            .one()
        )
        assert moved_allocation.decision_id is None, (
            "a reallocated hold belongs to no revision - tied to B's CURRENT decision it "
            "is one supersede away from reading gone"
        )

        # B is re-confirmed for an unrelated reason (the planner touching the same order
        # again); the reserve stands exactly as it settled - the frozen snapshot for this
        # product now reads a reserve component, not a fresh Buy.
        ProjectSupplyService(db).confirm(
            order_b,
            ConfirmSupplyBody(lines=[ConfirmLine(
                project_line_id=line_b.id,
                reserve=[ConfirmReserveComponent(warehouse_id=str(world["own"].id), qty="80")],
                buy_qty="0",
            )]),
            actor_user_id=world["actor"],
        )
        db.commit()

        db.expire_all()
        assert _hold_qty(db, line_b.id) == Decimal("80"), (
            "the reallocated reserve must survive B's next confirm, not read gone"
        )
        assert db.get(SOLineAllocation, moved_allocation.id).decision_id is None

        b_live_order_rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == line_b.id, OrderInquiryRow.verb == IV_ORDER,
                    OrderInquiryRow.state != INQUIRY_CANCELLED)
            .all()
        )
        assert b_live_order_rows == [], (
            "fully covered by the settled reserve - nothing raised again"
        )

        b_active_decision = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order_b.id,
                    SOSupplyDecision.state == DECISION_ACTIVE)
            .one()
        )
        snapshot = next(
            s for s in b_active_decision.line_snapshots if str(s.get("project_line_id")) == str(line_b.id)
        )
        assert snapshot["buy_qty"] == "0", snapshot
        assert snapshot.get("reserve_qty") == "80", snapshot


# --------------------------------------------------------------------------- #
# AC-D5: `_apply_placed_redirect` is gone, `redirected_to_pool` never written
# --------------------------------------------------------------------------- #

def test_apply_placed_redirect_is_gone_and_redirected_to_pool_is_never_written(api):
    assert not hasattr(planning_change_service, "_apply_placed_redirect"), (
        "AC-D5 (contract point 3): _apply_placed_redirect must be deleted, its job done "
        "by the D1/D2/D3 reallocation path instead"
    )

    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db
    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    redirected = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.redirected_to_pool.is_(True))
        .count()
    )
    assert redirected == 0


# --------------------------------------------------------------------------- #
# D4 (review round): a line the same batch re-decides is not a waiting need
# --------------------------------------------------------------------------- #


def test_a_line_the_same_batch_re_decides_never_receives_a_reallocation(api):
    """D4 (review round): `_waiting_rows` already carries an `exclude_line_ids` param
    with exactly this doctrine in its own docstring ("a line the same change is
    re-deciding is not a waiting need - its rows are in flux this very apply") - but
    neither `_redeal_document` nor `_move_reserve` ever passes it, so the exclusion is
    dead code. Two lines of the same product, one order, one batch: line 1 frees 34 of
    its placed PO qty (qty_down); line 2 carries an OLDER raised, unlinked ORDER row for
    the same product, due earlier, and is ALSO re-decided in this same batch (its own
    date moved). Line 1's own composed suggestion already says the freed 34 goes to the
    POOL (nothing waits for it once line 2 is properly excluded) - but at apply, line 2's
    row is still live when the redeal runs and gets linked to line 1's document instead,
    which is a different target than the one composed and confirmed."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="234",
                             required_date=date(2027, 3, 1))
    core_line2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50",
                             required_date=date(2027, 2, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line1)
    line2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_line2)
    db.commit()

    _confirm(client, order.id, {"lines": [
        _line_payload(line1.id, buy_qty="234", buy_reason="ZZT no stock anywhere"),
        _line_payload(line2.id, buy_qty="50", buy_reason="ZZT no stock anywhere"),
    ]})
    raised_row1 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line1.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    raised_row2 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line2.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("134"), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        raised_row1.id, [{"po_line_id": po_line.id, "qty": "134"}], actor_user_id=world.actor,
    )
    db.commit()

    # Write-first: line 1 drops (frees 34 of the placed 134); line 2 also changes in the
    # SAME batch (its date moves a little later, still earlier than line 1's).
    core_line1.qty_ordered = Decimal("100")
    line1.qty = Decimal("100")
    new_line2_date = date(2027, 2, 10)
    core_line2.required_date = new_line2_date
    line2.delivery_date = new_line2_date
    db.flush()

    changed1 = _diff_change(
        QTY_CHANGED, core_line1, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=date(2027, 3, 1), old_qty="234", new_qty="100",
    )
    changed2 = _diff_change(
        DATE_MOVED, core_line2, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 2, 1), new_date=new_line2_date, old_qty="50", new_qty="50",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed1, changed2])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={id(changed1): str(core_line1.id), id(changed2): str(core_line2.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    rows_out = out["orders"][0]["rows"]
    row1_out = next(r for r in rows_out if r["line_no"] == 1)
    reallocate = next(
        c for c in row1_out["suggestion"]["components"] if c["action"] == "reallocate"
    )
    assert reallocate["target"] == "pool", reallocate

    for r in rows_out:
        planning_change_service.set_row_decision(db, str(batch.id), str(r["id"]), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    # Line 2's own row (the same batch is re-deciding it right now) must carry no link
    # from line 1's document - it is not a waiting need, its rows are in flux this apply.
    row2_links = ProjectOrderInquiryService(db)._links_of(raised_row2.id)
    assert not any(str(l.po_line_id) == str(po_line.id) for l in row2_links), row2_links

    # The executed target equals the composed one: the freed 34 lands on a pool row.
    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    assert pool_rows[0].qty == Decimal("34")
    pool_links = ProjectOrderInquiryService(db)._links_of(pool_rows[0].id)
    assert {str(l.po_line_id) for l in pool_links} == {str(po_line.id)}


def test_the_batch_records_where_the_quantity_went(api):
    """D5 (review round): `PlanningChangeRow.result_json` is documented on the model
    itself as "what Apply wrote for this row alone ... read back beside `applied_reason`
    on the batch page after Apply" - the field the coder's own comment names for exactly
    this. Measured directly: today it is only `{"board_link": ..., "confirmed": True}` -
    it names nothing about where a reallocated quantity actually went, so the batch page
    cannot say what happened to it. This asserts `result_json` gets an
    `executed_reallocations` list of plain-English strings, one per `reallocate`
    component, equal to the SAME text the composed suggestion used (`component["label"]`)
    when nothing in the world changed between compose and apply - "the executed target
    equals the label's target"."""
    from app.models.planning_change import PlanningChangeRow

    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db
    composed_row = _only_row(db, batch)
    reallocate = next(
        c for c in composed_row.suggestion_json["components"] if c["action"] == "reallocate"
    )
    composed_label = reallocate["label"]

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    assert composed_label in executed, (composed_label, fresh.result_json)


def test_a_receiving_row_covered_exactly_reads_placed_not_partly_linked():
    """D6 (review round): `_move_reserve` reduces the receiving row's `qty` by what it
    takes but never recomputes its `state` - `ProjectOrderInquiryService._coverage_state`
    is the one formula every other writer uses ("linked + bundled >= qty reads placed"),
    and `_move_reserve` is not one of its callers. A receiving row of 80 already
    partly-linked 46 elsewhere, that then receives a reserve move of exactly 34 (the
    giver's whole hold), settles its qty to 46 - now EXACTLY what is already linked - and
    must read `placed`, not the stale `partly_linked` from before the move."""
    today = date.today()
    a_required = today + timedelta(days=20)
    a_new = today + timedelta(days=45)  # inside the reserve window
    b_required = today + timedelta(days=30)  # earlier than A's new date

    with blank_session() as db:
        world = _held_reserve_world(db, qty="34", required_date=a_required)
        order_b, line_b, core_so_b, core_line_b = _seed_order(
            db, world["company_id"], world["project"], world["product"], world["own"],
            qty="80", required_date=b_required,
        )
        ProjectSupplyService(db).confirm(
            order_b,
            ConfirmSupplyBody(lines=[ConfirmLine(
                project_line_id=line_b.id, buy_qty="80", buy_reason="ZZT no stock anywhere",
            )]),
            actor_user_id=world["actor"],
        )
        db.commit()
        b_row = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == line_b.id, OrderInquiryRow.verb == IV_ORDER)
            .one()
        )

        from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        supplier = Supplier(
            id=_uid(), company_id=world["company_id"], supplier_code=f"ZZT-{_uid()[:8]}",
            supplier_name=f"{MARKER} supplier",
        )
        po = PurchaseOrder(
            id=_uid(), company_id=world["company_id"], po_number=f"ZZT-PO-{_uid()[:8]}",
            supplier_id=supplier.id,
        )
        db.add_all([supplier, po])
        db.flush()
        po_line = PurchaseOrderLine(
            id=_uid(), company_id=world["company_id"], purchase_order_id=po.id,
            product_id=world["product"].id, warehouse_id=world["own"].id,
            qty_ordered=Decimal("46"), qty_received=Decimal("0"), line_status="open",
        )
        db.add(po_line)
        db.commit()
        ProjectOrderInquiryService(db).place_on_po_allocations(
            b_row.id, [{"po_line_id": po_line.id, "qty": "46"}], actor_user_id=world["actor"],
        )
        db.commit()
        db.expire_all()
        b_row = db.get(OrderInquiryRow, b_row.id)
        assert b_row.state == INQUIRY_PARTLY_LINKED
        assert b_row.qty == Decimal("80")

        batch = _change_and_batch(db, world, new_required_date=a_new)
        row = _seam_only_row(db, batch)
        planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
        result = planning_change_service.apply(db, str(batch.id), world["actor"])
        db.commit()
        assert result["failed_orders"] == [], result["failed_orders"]

        db.expire_all()
        b_row = db.get(OrderInquiryRow, b_row.id)
        assert b_row.qty == Decimal("46")
        links = ProjectOrderInquiryService(db)._links_of(b_row.id)
        assert sum(Decimal(str(l.qty)) for l in links) == Decimal("46")
        assert b_row.state == INQUIRY_PLACED, b_row.state


def test_a_freed_spo_share_is_unlinked_and_named_unallocated(api):
    """D7 (review round): `_release_components`'s "spo" branch always says "Reallocate
    SPO {qty} to {target}" - an instruction promising a redeal - but `_redeal_document`
    can never carry one out (its own comment: "an SPO share has no purchase-order line to
    re-deal ... left for a person"). Measured directly: apply leaves the SPO link exactly
    as it was, the order-back row stays `placed`, and nothing about it appears anywhere
    in `result_json` - the suggestion said "Reallocate ... to pool" and NOTHING happened,
    which is the rule this test names: never record an instruction that is not carried
    out. The held SPO 100 delayed past its window must instead compose a `release`
    (never `reallocate`) naming no target, and reading "unallocated for purchasing" - and
    apply must actually unlink it, freeing the SPOAllocation for purchasing to see."""
    from app.models.planning_change import PlanningChangeRow

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    near = date.today() + timedelta(days=10)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="100",
                            required_date=near)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    # A real held SPO share: an ORDER_BACK row linked to a real SPOAllocation, exactly
    # the shape `place_on_po_allocations` writes for one (AC-I6's own rule: only an
    # ORDER_BACK row may name an allocation). Seeded directly rather than driven through
    # `confirm()`'s live ladder, which would need a whole buying-group world to offer 100
    # of real water - the FROZEN state is what this test is about, not how it got there.
    spo = _spo(db, world.product, world.own_wh, qty="100", arrives=near)
    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state=INQUIRY_RAISED, raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    order_back_row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("100"), verb=IV_ORDER_BACK, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(order_back_row)
    db.flush()
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=order_back_row.id,
        spo_allocation_id=spo.id, document=spo.spo_number, qty=Decimal("100"),
    )
    db.add(link)
    db.commit()

    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE,
        line_snapshots=[{
            "project_line_id": str(line.id), "line_no": 1,
            "item_code": world.product.product_code,
            "buy_qty": "0", "reserve_qty": "0", "borrow_qty": "0",
            "timely_spo_qty": "100", "timely_spo_refs": [spo.spo_number],
            "required_date": near.isoformat(), "product_id": str(world.product.id),
            "core_line_id": str(core_line.id),
            "components": [{
                "kind": "timely_spo", "qty": "100",
                "source_location": world.own_wh.warehouse_code,
            }],
        }],
        confirmed_by=world.actor, confirmed_at=None,
    )
    db.add(decision)
    db.commit()

    # Write-first: the book delays this line far past the window - the water it held no
    # longer applies, and the re-run proposes none for the new date.
    far = date.today() + timedelta(days=400)
    core_line.required_date = far
    db.commit()

    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=near, new_date=far, old_qty="100", new_qty="100",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    out = planning_change_service.get_batch(db, str(batch.id))
    row_out = out["orders"][0]["rows"][0]
    spo_component = next(
        c for c in row_out["suggestion"]["components"] if c.get("source") == "spo"
    )
    assert spo_component["action"] == "release", spo_component
    assert not spo_component.get("target"), spo_component
    assert "Reallocate" not in spo_component["label"], spo_component
    assert "unallocated for purchasing" in spo_component["label"], spo_component

    row = _only_row(db, batch)
    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    remaining_links = ProjectOrderInquiryService(db)._links_of(order_back_row.id)
    assert remaining_links == [], (
        "the SPO link must be removed - never record an instruction (Reallocate) that "
        "is not carried out"
    )
    spo_links = db.query(OrderInquiryLink).filter(OrderInquiryLink.spo_allocation_id == spo.id).all()
    linked_total = sum(Decimal(str(l.qty)) for l in spo_links)
    assert spo.allocated_quantity - linked_total == Decimal("100"), (
        "the incoming list's unallocated quantity for this SPO line must read 100 again"
    )

    fresh = db.get(PlanningChangeRow, row.id)
    released = (fresh.result_json or {}).get("released_documents") or []
    assert spo.spo_number in released, fresh.result_json


# --------------------------------------------------------------------------- #
# Rule 6: a cancelled line's placed quantity with no same-order taker
# --------------------------------------------------------------------------- #

def test_a_cancelled_lines_placed_quantity_with_no_same_order_taker_follows_rule_6(api):
    """Order A's line is wholly Buy, wholly placed on a real PO (34), no other line of A
    carries this product. Order B has a raised, unlinked ORDER row for the SAME product,
    due EARLIER. Removing A's line has nowhere to shift the placement to on A's own order
    (`_shift_links_off_retired_lines` only looks at survivors of the SAME order) - rule 6
    says the whole placement still has to go somewhere, cross-order, the same way a
    confirmed row's freed PO quantity would (`_execute_reallocations`'s own
    `_redeal_document`), which is exactly what `_execute_reallocations` skips for a
    cancelled row today (`kind != "cancelled"`).
    """
    world, core_so, core_line, order, line, po, po_line = _wholly_placed_buy_world(api)
    db = world.db
    client = api[0]

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="50",
                                  required_date=date(2027, 2, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="50", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    batch = _cancel_the_line(db, world, core_so, core_line)
    row = _only_row(db, batch)
    assert row.kind == "cancelled", row.kind
    reallocate_components = [
        c for c in (row.suggestion_json or {}).get("components", [])
        if c.get("action") == "reallocate"
    ]
    assert len(reallocate_components) == 1, row.suggestion_json
    assert f"{other_so.so_number} ORDER" in reallocate_components[0]["label"], (
        reallocate_components[0]
    )

    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    other_row = db.get(OrderInquiryRow, other_row.id)
    links = _links_of(db, other_row.id)
    assert sum(Decimal(str(l.qty)) for l in links) == Decimal("34"), links
    assert other_row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED), other_row.state
    assert other_row.note and f"Found: {po.po_number} 34" in other_row.note, other_row.note

    from app.models.procurement import PurchaseOrderLine as _POLine

    fresh_po_line = db.get(_POLine, po_line.id)
    po_links = (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == fresh_po_line.id).all()
    )
    po_linked_total = sum(Decimal(str(l.qty)) for l in po_links)
    assert po_linked_total == fresh_po_line.qty_ordered, (
        "the PO line must read fully claimed", po_linked_total, fresh_po_line.qty_ordered
    )

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert any(
        po.po_number in item and "34" in item and f"{other_so.so_number} ORDER" in item
        for item in executed
    ), fresh.result_json
    assert not any(po.po_number in item for item in released), fresh.result_json


def test_a_cancelled_lines_placed_quantity_lands_on_a_pool_row_when_nobody_needs_it(api):
    """Same shape, no order B: nobody waiting for the product anywhere, so the whole
    placement has to land on a pool-location row instead (the "last resort" leg of rule 6,
    the same shape a confirmed row's freed PO quantity gets via `_pool_row_for`), rather
    than the released-document/qty-0 outcome `_shift_links_off_retired_lines` gives it
    today when it finds no same-order survivor.
    """
    world, core_so, core_line, order, line, po, po_line = _wholly_placed_buy_world(api)
    db = world.db

    batch = _cancel_the_line(db, world, core_so, core_line)
    row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    assert pool_rows[0].qty == Decimal("34"), pool_rows[0].qty
    pool_links = _links_of(db, pool_rows[0].id)
    assert sum(Decimal(str(l.qty)) for l in pool_links) == Decimal("34"), pool_links

    from app.models.procurement import PurchaseOrderLine as _POLine

    fresh_po_line = db.get(_POLine, po_line.id)
    po_links = (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == fresh_po_line.id).all()
    )
    po_linked_total = sum(Decimal(str(l.qty)) for l in po_links)
    assert po_linked_total == fresh_po_line.qty_ordered, (
        "the PO line must read fully claimed against the pool row", po_linked_total,
        fresh_po_line.qty_ordered,
    )

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert any(po.po_number in item and "34" in item and "pool" in item.lower()
               for item in executed), fresh.result_json
    assert not any(po.po_number in item for item in released), fresh.result_json


# --------------------------------------------------------------------------- #
# Reviewer blocker B1: every link of a cancelled row finds a taker
# --------------------------------------------------------------------------- #

def test_every_link_of_a_cancelled_row_finds_a_taker_survivor_and_cross_order(api):
    """Line 1's placement sits on TWO purchase-order lines of 17 each. Line 2 (same order)
    has exactly 17 of headroom - enough to take ONE of the two links whole, nothing left
    for the other. Order B elsewhere has a raised, unlinked ORDER row for the product.
    Cancelling line 1 must move BOTH links: one to line 2 (the same-order survivor), the
    other cross-order to B - never leave one stranded on the row that no longer owes
    anybody anything.

    Today `_shift_links_off_retired_lines` decides per LINK (line 2 takes link A, link B is
    correctly left "for rule six" since nobody else on this order can take it) but
    `_apply_one_order` passes `shifted_by_line.keys()` - keyed per LINE, not per link - as
    `already_shifted_line_ids` to `_execute_reallocations`. Because line 1's key IS in
    `shifted_by_line` (link A succeeded), the WHOLE row is excluded from that cascade, so
    link B is never picked up by anybody and stays linked to the now-cancelled row.
    """
    fixture = _two_lines_split_po_world(api)
    world = fixture["world"]
    db = world.db
    client = api[0]
    core_so = fixture["core_so"]
    core_line_1 = fixture["core_line_1"]
    po = fixture["po"]
    row_1 = fixture["row_1"]
    row_2 = fixture["row_2"]

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="17",
                                  required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="17", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    batch = _cancel_the_line(db, world, core_so, core_line_1)
    row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    cancelled_row = db.get(OrderInquiryRow, row_1.id)
    remaining_links = _links_of(db, cancelled_row.id)
    assert remaining_links == [], (
        "every link of a cancelled row must find a taker - none may stay on the row that "
        "no longer owes anybody anything",
        remaining_links,
    )

    survivor_row = db.get(OrderInquiryRow, row_2.id)
    survivor_links = _links_of(db, survivor_row.id)
    assert len(survivor_links) == 1, survivor_links
    assert sum(Decimal(str(l.qty)) for l in survivor_links) == Decimal("17"), survivor_links

    other_row = db.get(OrderInquiryRow, other_row.id)
    other_links = _links_of(db, other_row.id)
    assert sum(Decimal(str(l.qty)) for l in other_links) == Decimal("17"), other_links
    assert other_row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED), other_row.state
    assert other_row.note and f"Found: {po.po_number} 17" in other_row.note, other_row.note

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert len(executed) == 2, (
        "both the survivor shift AND the cross-order deal must be reported", fresh.result_json
    )
    assert released == [], fresh.result_json


def test_every_link_of_a_cancelled_row_finds_a_taker_survivor_then_release_when_nobody_needs_it(
    api,
):
    """Same shape, no order B, no pool warehouse configured for this line's location: the
    link line 2 cannot take must be RELEASED (unlinked, named in `released_documents`) -
    never left stranded on the cancelled row either.
    """
    no_pool_wh = _warehouse(api[1].db, f"ZZT-NOPOOL-{_uid()[:4]}", segment="project")
    fixture = _two_lines_split_po_world(api, warehouse=no_pool_wh)
    world = fixture["world"]
    db = world.db
    core_so = fixture["core_so"]
    core_line_1 = fixture["core_line_1"]
    row_1 = fixture["row_1"]
    row_2 = fixture["row_2"]

    batch = _cancel_the_line(db, world, core_so, core_line_1, location=no_pool_wh.warehouse_code)
    row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    cancelled_row = db.get(OrderInquiryRow, row_1.id)
    remaining_links = _links_of(db, cancelled_row.id)
    assert remaining_links == [], (
        "every link of a cancelled row must find a taker or be released - none may stay "
        "on the row that no longer owes anybody anything",
        remaining_links,
    )

    survivor_row = db.get(OrderInquiryRow, row_2.id)
    survivor_links = _links_of(db, survivor_row.id)
    assert len(survivor_links) == 1, survivor_links
    assert sum(Decimal(str(l.qty)) for l in survivor_links) == Decimal("17"), survivor_links

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert len(executed) == 1, (
        "only the survivor shift is an executed reallocation", fresh.result_json
    )
    assert len(released) == 1, (
        "the link nobody could take must be released and named", fresh.result_json
    )


def test_a_cancelled_lines_placed_buy_with_no_pool_configured_is_released_not_executed(api):
    """R3: a cancelled line's placed Buy, no same-order survivor, no waiting row anywhere,
    and NO pool warehouse configured for its location - the link is removed (not stranded),
    and the sentence names it in `released_documents`, never `executed_reallocations`.

    Today `_redeal_document`'s no-pool branch (~3274) appends the "Release ... unallocated
    for purchasing" sentence, but its caller (`_execute_reallocations`, ~3623) always
    extends `done[row_id]["executed_reallocations"]` with whatever `_redeal_document`
    returns - so a release sentence lands in the wrong list.
    """
    no_pool_wh = _warehouse(api[1].db, f"ZZT-NOPOOL2-{_uid()[:4]}", segment="project")
    world, core_so, core_line, order, line, po, po_line = _wholly_placed_buy_world(
        api, warehouse=no_pool_wh
    )
    db = world.db

    batch = _cancel_the_line(db, world, core_so, core_line, location=no_pool_wh.warehouse_code)
    row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    cancelled_row = db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == line.id
    ).one()
    assert _links_of(db, cancelled_row.id) == [], _links_of(db, cancelled_row.id)

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert not any("unallocated for purchasing" in item for item in executed), (
        "a release sentence must never land in executed_reallocations", fresh.result_json
    )
    assert any(
        po.po_number in item and "unallocated for purchasing" in item for item in released
    ), fresh.result_json


# --------------------------------------------------------------------------- #
# Reviewer probe P4: a freed document split across a waiting row and the pool
# --------------------------------------------------------------------------- #

def _split_across_two_po_lines_world(api, *, warehouse=None):
    """A single held Buy line (no other line of the order carrying this product), its
    WHOLE quantity placed across TWO real purchase-order lines of 17 each - no same-order
    survivor at all, so both links must be re-dealt cross-order/pool."""
    client, world = api
    db = world.db
    wh = warehouse or world.own_wh
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, wh, qty_ordered="34",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="34", buy_reason="ZZT no stock anywhere"),
    ]})
    row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line_a = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=wh.id,
        qty_ordered=Decimal("17"), qty_received=Decimal("0"), line_status="open",
    )
    po_line_b = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=wh.id,
        qty_ordered=Decimal("17"), qty_received=Decimal("0"), line_status="open",
    )
    db.add_all([po_line_a, po_line_b])
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        row.id,
        [
            {"po_line_id": po_line_a.id, "qty": "17"},
            {"po_line_id": po_line_b.id, "qty": "17"},
        ],
        actor_user_id=world.actor,
    )
    db.commit()
    db.expire_all()
    row = db.get(OrderInquiryRow, row.id)
    assert row.state == INQUIRY_PLACED, row.state
    return {
        "world": world, "core_so": core_so, "core_line": core_line, "order": order,
        "line": line, "po": po, "po_line_a": po_line_a, "po_line_b": po_line_b, "row": row,
    }


def test_a_freed_document_split_across_a_waiting_row_and_the_pool_lands_both_legs(api):
    """A cancelled line's Buy 34 sits on TWO purchase-order lines of 17 each; no same-
    order survivor at all. Order B's raised, unlinked ORDER row has headroom 17 - LESS
    than the whole 34 - and a pool warehouse IS configured, so the remainder must land on
    a pool row: one leg to the waiting row, the other to the pool, never both stranded on
    the cancelled row nor both piled onto the same taker.

    Today `_unclaim_shares` (planning_change_service.py ~3073) deletes a link without
    calling `service._invalidate_link_cache()` - so when the SECOND `place_on_po_
    allocations` of the same apply pass (the pool leg, after order B's leg already ran)
    checks the po line's own claimed total, it reads a STALE, still-fully-claimed memo
    and refuses with `order_inquiry_po_line_short`; the order's savepoint fails and it
    lands in `failed_orders`.
    """
    fixture = _split_across_two_po_lines_world(api)
    world = fixture["world"]
    db = world.db
    client = api[0]
    core_so = fixture["core_so"]
    core_line = fixture["core_line"]
    po = fixture["po"]
    row = fixture["row"]

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="17",
                                  required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="17", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    batch = _cancel_the_line(db, world, core_so, core_line)
    change_row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    cancelled_row = db.get(OrderInquiryRow, row.id)
    assert _links_of(db, cancelled_row.id) == [], _links_of(db, cancelled_row.id)

    other_row = db.get(OrderInquiryRow, other_row.id)
    other_links = _links_of(db, other_row.id)
    assert len(other_links) == 1, other_links
    assert sum(Decimal(str(l.qty)) for l in other_links) == Decimal("17"), other_links
    assert other_row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED), other_row.state

    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    pool_links = _links_of(db, pool_rows[0].id)
    assert len(pool_links) == 1, pool_links
    assert sum(Decimal(str(l.qty)) for l in pool_links) == Decimal("17"), pool_links

    # Each PO line claimed exactly once - by the waiting row XOR the pool row, never both,
    # never neither.
    po_line_ids = {fixture["po_line_a"].id, fixture["po_line_b"].id}
    claimed_po_line_ids = {l.po_line_id for l in other_links} | {l.po_line_id for l in pool_links}
    assert claimed_po_line_ids == po_line_ids, (other_links, pool_links)
    assert {l.po_line_id for l in other_links} != {l.po_line_id for l in pool_links}

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, change_row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert len(executed) == 2, fresh.result_json
    assert any(po.po_number in item and "17" in item for item in executed), fresh.result_json
    assert released == [], fresh.result_json


def test_a_freed_document_lands_on_survivor_waiting_row_and_pool_three_way(api):
    """Same shape, widened: line 1's own quantity is 51 (the two original 17-unit PO
    lines plus a third), placed wholly across THREE purchase-order lines of 17. A same-
    order survivor with headroom 17 takes its own leg, the waiting row takes a second, and
    the pool takes the third - three purchase-order lines of 17, three different
    destinations, none stranded and none double-claimed."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="51",
                              required_date=date(2027, 3, 1))
    core_line_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="17",
                              required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_line_1)
    line_2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_line_2)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line_1.id, buy_qty="51", buy_reason="ZZT no stock anywhere"),
        _line_payload(line_2.id, buy_qty="17", buy_reason="ZZT no stock anywhere"),
    ]})
    row_1 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_1.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    row_2 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_lines = []
    for _ in range(3):
        po_line = PurchaseOrderLine(
            id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
            product_id=world.product.id, warehouse_id=world.own_wh.id,
            qty_ordered=Decimal("17"), qty_received=Decimal("0"), line_status="open",
        )
        db.add(po_line)
        po_lines.append(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        row_1.id,
        [{"po_line_id": pl.id, "qty": "17"} for pl in po_lines],
        actor_user_id=world.actor,
    )
    db.commit()
    db.expire_all()
    row_1 = db.get(OrderInquiryRow, row_1.id)
    assert row_1.state == INQUIRY_PLACED, row_1.state

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="17",
                                  required_date=date(2027, 3, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="17", buy_reason="Nothing free elsewhere."),
    ]})
    other_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == other_project_line.id,
                OrderInquiryRow.verb == IV_ORDER)
        .one()
    )

    batch = _cancel_the_line(db, world, core_so, core_line_1)
    change_row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result["failed_orders"]

    db.expire_all()
    cancelled_row = db.get(OrderInquiryRow, row_1.id)
    assert _links_of(db, cancelled_row.id) == [], _links_of(db, cancelled_row.id)

    survivor_links = _links_of(db, row_2.id)
    assert len(survivor_links) == 1, survivor_links
    assert sum(Decimal(str(l.qty)) for l in survivor_links) == Decimal("17"), survivor_links

    other_row = db.get(OrderInquiryRow, other_row.id)
    other_links = _links_of(db, other_row.id)
    assert len(other_links) == 1, other_links
    assert sum(Decimal(str(l.qty)) for l in other_links) == Decimal("17"), other_links

    pool_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.is_(None), OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.stock_location == world.pool_wh.warehouse_code)
        .all()
    )
    assert len(pool_rows) == 1, pool_rows
    pool_links = _links_of(db, pool_rows[0].id)
    assert len(pool_links) == 1, pool_links
    assert sum(Decimal(str(l.qty)) for l in pool_links) == Decimal("17"), pool_links

    claimed_po_line_ids = (
        {l.po_line_id for l in survivor_links}
        | {l.po_line_id for l in other_links}
        | {l.po_line_id for l in pool_links}
    )
    assert claimed_po_line_ids == {pl.id for pl in po_lines}, (
        survivor_links, other_links, pool_links,
    )

    from app.models.planning_change import PlanningChangeRow

    fresh = db.get(PlanningChangeRow, change_row.id)
    executed = (fresh.result_json or {}).get("executed_reallocations") or []
    released = (fresh.result_json or {}).get("released_documents") or []
    assert len(executed) == 3, fresh.result_json
    assert released == [], fresh.result_json


def test_the_wire_carries_the_cancelled_rows_reallocation_result_and_null_for_pending(api):
    """R1: `row_out()` (`planning_change_service.py` ~2231-2256) builds the wire dict for
    one row and never mentions `result_json` at all - confirmed by direct read (attempt 7
    browser walk) while trying to read a just-applied cancelled row's reallocation result
    off `GET .../planning-changes/{batch_id}` and finding no such key anywhere in the
    response. `PlanningChangeRow.result_json` is documented on the model itself as "what
    Apply wrote for this row alone ... read back beside `applied_reason` on the batch page
    after Apply" - so the wire needs a `result` key carrying it, `None` before Apply runs
    (nothing has been written yet) and the row's own `result_json` (with its
    `executed_reallocations`/`released_documents` sentences, per
    `test_a_cancelled_lines_placed_quantity_with_no_same_order_taker_follows_rule_6`) once
    Apply has. `response_model` silently drops an undeclared field, so this is asserted on
    the actual wire response, not the ORM row."""
    world, core_so, core_line, order, line, po, po_line = _wholly_placed_buy_world(api)
    db = world.db
    client = api[0]

    other_so = _core_so(db, world.company_id)
    other_line_core = _core_line(db, other_so, world.product, world.own_wh, qty_ordered="50",
                                  required_date=date(2027, 2, 1))
    other_order = _project_so(db, world.project, so_id=other_so.id,
                               autocount_doc_no=other_so.so_number)
    other_project_line = _project_line(db, other_order, line_no=1, product=world.product,
                                        core_line=other_line_core)
    db.commit()
    _confirm(client, other_order.id, {"lines": [
        _line_payload(other_project_line.id, buy_qty="50", buy_reason="Nothing free elsewhere."),
    ]})

    batch = _cancel_the_line(db, world, core_so, core_line)
    row = _only_row(db, batch)
    assert row.kind == "cancelled", row.kind

    pending_detail = client.get(f"{BASE}/planning-changes/{batch.id}")
    assert pending_detail.status_code == 200, pending_detail.text
    pending_orders = pending_detail.json()["orders"]
    pending_row = next(o for o in pending_orders if o["project_sales_order_id"] == str(order.id))
    pending_wire_row = pending_row["rows"][0]
    assert pending_wire_row["result"] is None, pending_wire_row

    put = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row.id}", json={"decision": "confirm"},
    )
    assert put.status_code == 200, put.text

    apply_response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["failed_orders"] == [], apply_response.json()

    applied_detail = client.get(f"{BASE}/planning-changes/{batch.id}")
    assert applied_detail.status_code == 200, applied_detail.text
    applied_orders = applied_detail.json()["orders"]
    applied_row = next(o for o in applied_orders if o["project_sales_order_id"] == str(order.id))
    applied_wire_row = applied_row["rows"][0]

    result = applied_wire_row["result"]
    assert result is not None, applied_wire_row
    executed = result.get("executed_reallocations") or []
    assert any(
        po.po_number in item and "34" in item and f"{other_so.so_number} ORDER" in item
        for item in executed
    ), result
    assert result.get("released_documents") == [], result
