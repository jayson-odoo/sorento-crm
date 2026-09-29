"""Lane REDEAL-CLOSED-PO: a planning-change Confirm never fails an order over a purchase-order
line that closed between compose and apply (SO396347, prod, 29 Sep 2026).

The shape: a pending batch row names a `reallocate` of placed purchase-order quantity
(`suggestion_json["components"]`, action `reallocate`, `qty_now` the freed amount). Between
the upload and the Confirm, the sync received that purchase-order line in full and marked it
`closed`. `_redeal_document` (`planning_change_service.py`) then re-links the freed share
through `place_on_po_allocations`, which refuses any line whose `line_status != "open"`
(`project_order_inquiry_service.py`, `_refuse_absent_target`: "That purchase order line is no
longer open."), and the per-order savepoint in `apply` rolls the WHOLE order back: "0 of 1
orders confirmed".

Owner direction (29 Sep): the confirm is too restrictive. One line's stale source must not
refuse the order; the order confirms, the affected share is skipped with a clear notice that
names the AutoCount line, and the linkage on a received line is purchasing's to adjust, never
the planning side's to re-link or to fail over.

Fixtures imported rather than copied, the same convention every other planning-change file in
this domain uses:
- `tests.scm.test_planning_change_reallocation` (`_drop_line_to_100`: 234 wholly Buy, 134
  placed on a real PO line, 100 raised unlinked, dropped to 100 - composes a `reallocate`
  for the freed 34 against a REAL `PurchaseOrderLine`).
- `tests.test_planning_changes` (`api` fixture, `_confirm`, `_line_payload`, `_diff_change`,
  `_core_so`, `_core_line`, `_project_so`, `_project_line`, `_uid`, `MARKER`).

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.planning_change import PlanningChangeRow
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import IV_ORDER, OrderInquiryLink, OrderInquiryRow
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import QTY_CHANGED, Diff

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    MARKER,
    api,
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _project_line,
    _project_so,
    _uid,
)
from tests.scm.test_planning_change_reallocation import _drop_line_to_100


def _only_row(db, batch) -> PlanningChangeRow:
    return db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == batch.id).one()


def _links_on_po_line(db, po_line_id) -> list:
    return db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == po_line_id).all()


def _receive_in_full(db, po_line: PurchaseOrderLine) -> None:
    """What the sync writes once the last unit lands: fully received, line closed."""
    po_line.qty_received = po_line.qty_ordered
    po_line.line_status = "closed"
    db.commit()


def test_a_closed_po_line_in_the_share_is_skipped_with_a_notice_and_the_order_confirms(api):
    """The SO396347 shape: the row's WHOLE placed share sits on one purchase-order line that
    the sync closed (received in full) after the batch was built. Today: 409
    `order_inquiry_po_line_closed` out of `place_on_po_allocations`, the order's savepoint
    rolls back, `failed_orders` names it. Expected: the order confirms; the row's
    `result_json["released_documents"]` carries a notice naming the purchase order and the
    sales-order line, saying the quantity was received and nothing was moved; no new link is
    written on the closed line (its received quantity is stock, and whatever link the line
    still holds on it is purchasing's to adjust)."""
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db

    po_line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).one()
    own_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()
    assert [str(l.row_id) for l in _links_on_po_line(db, po_line.id)] == [str(own_row.id)]

    row = _only_row(db, batch)
    components = (row.suggestion_json or {}).get("components") or []
    assert any(c.get("action") == "reallocate" for c in components), row.suggestion_json

    _receive_in_full(db, po_line)

    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()

    assert result["failed_orders"] == [], (
        "a purchase-order line that closed between compose and apply must not fail the "
        f"order: {result}"
    )
    assert result["applied_orders"] == [order.autocount_doc_no], result

    db.expire_all()
    fresh = db.get(PlanningChangeRow, row.id)
    assert fresh.applied_state == "applied", (fresh.applied_state, fresh.applied_reason)
    released = (fresh.result_json or {}).get("released_documents") or []
    notice = next((text for text in released if po.po_number in text), None)
    assert notice is not None, (released, fresh.result_json)
    assert "received" in notice, notice
    assert "nothing to move" in notice, notice
    # Names the AutoCount line the batch row is about, not only the purchase order.
    assert core_so.so_number in notice and f"line {line.line_no}" in notice, notice

    # No row was placed onto the closed line by this apply: every link it carries, if any,
    # is still the line's own row's (history of what covered it), never a pool row's or a
    # stranger's.
    for link in _links_on_po_line(db, po_line.id):
        assert str(link.row_id) == str(own_row.id), (link.row_id, own_row.id)


def _placed_on_two_pos_world(api):
    """234 wholly Buy, placed 100 on PO A and 134 on PO B (both open at placement time), then
    the book drops the line to 100 - freeing 134 of the placed quantity. The batch is built
    while both lines are still open, the way the SO396347 batch was. PO A alone cannot carry
    the whole freed 134, so the closed PO B share is genuinely reached by the re-deal."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="234",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="234", buy_reason="ZZT no stock anywhere"),
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
    po_a = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-POA-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    po_b = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-POB-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po_a, po_b])
    db.flush()
    po_line_a = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po_a.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("100"), qty_received=Decimal("0"), line_status="open",
    )
    po_line_b = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po_b.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("134"), qty_received=Decimal("0"), line_status="open",
    )
    db.add_all([po_line_a, po_line_b])
    db.commit()
    ProjectOrderInquiryService(db).place_on_po_allocations(
        raised_row.id,
        [
            {"po_line_id": po_line_a.id, "qty": "100"},
            {"po_line_id": po_line_b.id, "qty": "134"},
        ],
        actor_user_id=world.actor,
    )
    db.commit()

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
    return world, core_so, order, line, raised_row, po_a, po_line_a, po_b, po_line_b, batch


def test_the_open_share_still_moves_when_a_sibling_po_line_closed(api):
    """Two purchase-order lines under one placed row, one of them received and closed by
    apply time, and the open one too small to carry the whole freed quantity. Today the
    re-deal reaches the closed line and the order fails. Expected: the closed share is
    skipped with its notice; the OPEN share is still re-dealt exactly as before (here:
    nobody else needs it, so it lands on a pool row linked to PO A only). Nothing is ever
    written onto PO B, and PO A is never over-linked."""
    world, core_so, order, line, own_row, po_a, po_line_a, po_b, po_line_b, batch = (
        _placed_on_two_pos_world(api)
    )
    db = world.db
    row = _only_row(db, batch)
    components = (row.suggestion_json or {}).get("components") or []
    assert any(c.get("action") == "reallocate" for c in components), row.suggestion_json

    _receive_in_full(db, po_line_b)

    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()

    assert result["failed_orders"] == [], result
    assert result["applied_orders"] == [order.autocount_doc_no], result

    db.expire_all()
    fresh = db.get(PlanningChangeRow, row.id)
    assert fresh.applied_state == "applied", (fresh.applied_state, fresh.applied_reason)
    said = fresh.result_json or {}
    released = said.get("released_documents") or []
    assert any(po_b.po_number in text and "received" in text for text in released), said
    executed = said.get("executed_reallocations") or []
    assert any(po_a.po_number in text for text in executed), said
    assert not any(po_b.po_number in text for text in executed), said

    # PO B: only the line's own row ever sat on it.
    for link in _links_on_po_line(db, po_line_b.id):
        assert str(link.row_id) == str(own_row.id), (link.row_id, own_row.id)
    # PO A: the freed open share found a pool row, and the line is never over-linked.
    links_a = _links_on_po_line(db, po_line_a.id)
    assert sum((Decimal(str(l.qty)) for l in links_a), Decimal("0")) <= Decimal("100"), links_a
    pool_links = [l for l in links_a if str(l.row_id) != str(own_row.id)]
    assert pool_links, links_a
    pool_row = db.get(OrderInquiryRow, pool_links[0].row_id)
    assert pool_row.so_line_id is None, "the freed open share belongs to the pool now"
    assert pool_row.stock_location == world.pool_wh.warehouse_code
