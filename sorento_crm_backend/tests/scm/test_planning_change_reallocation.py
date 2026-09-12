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

from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_CANCELLED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services import planning_change_service
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.outstanding_diff import QTY_CHANGED, Diff

from tests._pg_fixture import blank_session
from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    api,
    _classification,
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _project_line,
    _project_so,
)
from tests.scm.test_planning_change_recompute_and_diff import (
    _only_row,
    _qty_down_with_po_world,
)
from tests.scm.test_planning_change_delta_seam import (
    _change_and_batch,
    _held_reserve_world,
    _seed_order,
)
from tests.scm.test_planning_change_delta_seam import _only_row as _seam_only_row
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

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
    assert po.qty_ordered - total_linked == Decimal("0")


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

        a_hold = (
            db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == world["line"].id,
                    SOLineAllocation.confirmed_at.isnot(None))
            .all()
        )
        assert sum(Decimal(str(a.qty)) for a in a_hold) == Decimal("0"), a_hold

        a_live_rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == world["line"].id,
                    OrderInquiryRow.verb == IV_ORDER, OrderInquiryRow.state != INQUIRY_CANCELLED)
            .all()
        )
        assert len(a_live_rows) == 1, [(r.state, str(r.qty)) for r in a_live_rows]
        assert a_live_rows[0].qty == Decimal("134")
        assert a_live_rows[0].delivery_date == a_new


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
