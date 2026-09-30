"""The planning side never changes an Order Inquiry document link; it records intent.

`documentation/plans/scm/PLAN-oi-links-intent-only.md`, UAC
`oi-links-intent-only-acceptance-criteria.md` (AC-IO-1 to AC-IO-6). Owner ruling 29 Sep 2026,
verbatim: "shrinking a line shouldn't trim its own PO link, the quantity change is still at
the autocount side by the purchasing, a cancelled line shouldn't directly hand its PO link to
its sibling, new buy shouldn't get draft PO links also, the PO link is based on autocount
linkage as source of truth". RED before the code lands.

Fixtures imported rather than copied:
- `tests.scm.test_planning_change_reallocation` (`_drop_line_to_100`, `_two_lines_split_po_world`,
  `_cancel_the_line`, `_confirm_row_and_apply`, `_links_of`).
- `tests.scm.test_planning_change_redeal_closed_po_line` (`_placed_on_two_pos_world`,
  `_receive_in_full`, `_only_row`).
- `tests.test_planning_changes` (`api`, `_confirm`, `_line_payload`, `_diff_change`,
  `_core_so`, `_core_line`, `_project_so`, `_project_line`, `_uid`, `MARKER`).

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.planning_change import PlanningChangeRow
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
)
from app.services import planning_change_service
from app.services.scm.outstanding_diff import DATE_MOVED, Diff

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
from tests.scm.test_planning_change_reallocation import (
    _cancel_the_line,
    _confirm_row_and_apply,
    _drop_line_to_100,
    _links_of,
    _two_lines_split_po_world,
)
from tests.scm.test_planning_change_redeal_closed_po_line import (
    _only_row,
    _placed_on_two_pos_world,
    _receive_in_full,
)


def _po_links(db, po_line_id) -> list:
    return db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == po_line_id).all()


def _result_of(db, row_id) -> dict:
    return (db.get(PlanningChangeRow, row_id).result_json) or {}


def test_ac_io_1_qty_down_keeps_the_over_linked_po_link_and_names_it_for_purchasing(api):
    """AC-IO-1 (was AC-P3-8): 234 placed 134 on a PO line, dropped to 100. The row reads
    qty 100 and `placed`; its link still reads 134 (no trim, no unclaim); the PO line's
    linked total is unchanged; the note names the over-linked 34 as purchasing's to adjust
    in AutoCount."""
    world, core_so, core_line, order, line, po, batch = _drop_line_to_100(api)
    db = world.db

    row, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result

    db.expire_all()
    own_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()
    assert own_row.qty == Decimal("100"), own_row.qty
    assert own_row.state == INQUIRY_PLACED, own_row.state
    own_links = _links_of(db, own_row.id)
    assert sum(Decimal(str(l.qty)) for l in own_links) == Decimal("134"), (
        "the link is not trimmed by the planning side", own_links,
    )
    assert "AutoCount" in (own_row.note or ""), own_row.note

    po_line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).one()
    po_links = _po_links(db, po_line.id)
    assert {str(l.row_id) for l in po_links} == {str(own_row.id)}, po_links
    assert sum(Decimal(str(l.qty)) for l in po_links) == Decimal("134"), po_links


def test_ac_io_3_a_cancelled_line_keeps_both_links_and_the_survivor_gains_none(api):
    """AC-IO-3 (was AC-P3-6, the reviewer's B1 shape): line 1's placement on two PO lines
    of 17, line 2 (same order, same product) with headroom 17. Cancelling line 1 moves
    NOTHING: the survivor gains no link and no "Took" note, the cancelled row keeps both
    links, the PO lines stay claimed by the cancelled row, nothing is executed, and the
    batch records the intent for purchasing."""
    fixture = _two_lines_split_po_world(api)
    world = fixture["world"]
    db = world.db
    core_so = fixture["core_so"]
    po = fixture["po"]

    batch = _cancel_the_line(db, world, core_so, fixture["core_line_1"])
    row = _only_row(db, batch)
    _, result = _confirm_row_and_apply(db, batch, world.actor)
    assert result["failed_orders"] == [], result

    db.expire_all()
    cancelled_row = db.get(OrderInquiryRow, fixture["row_1"].id)
    assert cancelled_row.state == INQUIRY_CANCELLED, cancelled_row.state
    kept = _links_of(db, cancelled_row.id)
    assert {l.po_line_id for l in kept} == {fixture["po_line_a"].id, fixture["po_line_b"].id}, kept
    assert sum(Decimal(str(l.qty)) for l in kept) == Decimal("34"), kept

    survivor = db.get(OrderInquiryRow, fixture["row_2"].id)
    assert _links_of(db, survivor.id) == [], _links_of(db, survivor.id)
    assert "Took" not in (survivor.note or ""), survivor.note

    for po_line_id in (fixture["po_line_a"].id, fixture["po_line_b"].id):
        assert {str(l.row_id) for l in _po_links(db, po_line_id)} == {str(cancelled_row.id)}

    said = _result_of(db, row.id)
    assert not (said.get("executed_reallocations") or []), said
    notices = said.get("released_documents") or []
    assert any(po.po_number in text and "34" in text and "AutoCount" in text for text in notices), said


def test_ac_io_4_the_open_link_stays_when_a_received_link_redirects_the_row(api):
    """AC-IO-4 (was AC-RL-11's open-link release): a row placed 100 on an open PO line and
    134 on a PO line received in full since compose, dropped to 100. The settle may redirect
    the row, but the OPEN link stays on it exactly as it was, the received link stays as
    history, and nothing is written onto either line."""
    world, core_so, order, line, own_row, po_a, po_line_a, po_b, po_line_b, batch = (
        _placed_on_two_pos_world(api)
    )
    db = world.db
    _receive_in_full(db, po_line_b)

    row = _only_row(db, batch)
    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result

    db.expire_all()
    links_a = _po_links(db, po_line_a.id)
    assert [(str(l.row_id), Decimal(str(l.qty))) for l in links_a] == [
        (str(own_row.id), Decimal("100"))
    ], ("the open link stays on the row", links_a)
    links_b = _po_links(db, po_line_b.id)
    assert [(str(l.row_id), Decimal(str(l.qty))) for l in links_b] == [
        (str(own_row.id), Decimal("134"))
    ], ("the received link stays as history", links_b)


def test_ac_io_5_a_fresh_buy_gets_no_real_link_from_the_apply_cascade(api):
    """AC-IO-5 (G2, pinned): an unlinked Buy 50 on a line, an OPEN PO line of 50 for the
    product at the line's own warehouse, and a date-move batch applied. The apply's
    deferred cascade (`auto_place_for_confirmed_products`, door `decision_confirm`) writes
    no real document link on the row: at most a suggested link."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50",
                            required_date=date(2027, 3, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="50", buy_reason="ZZT no stock anywhere"),
    ]})
    buy_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    assert _links_of(db, buy_row.id) == []

    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id, status="active",
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("50"), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()

    new_date = date(2027, 3, 15)
    core_line.required_date = new_date
    line.delivery_date = new_date
    db.flush()
    changed = _diff_change(
        DATE_MOVED, core_line, doc_number=core_so.so_number,
        item_code=world.product.product_code, location=world.own_wh.warehouse_code,
        old_date=date(2027, 3, 1), new_date=new_date, old_qty="50", new_qty="50",
    )
    diff = Diff(scope_documents=(core_so.so_number,), changes=[changed])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(changed): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    row = _only_row(db, batch)
    planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "confirm")
    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()
    assert result["failed_orders"] == [], result

    db.expire_all()
    live_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    assert live_rows, "the line still owes purchasing a Buy"
    for live in live_rows:
        assert _links_of(db, live.id) == [], (
            "the planning side writes no real document link on a Buy row", live.id,
        )
    assert _po_links(db, po_line.id) == [], _po_links(db, po_line.id)
    # A suggested link is allowed (it is not a link): asserted only to be well-formed.
    for suggested in db.query(OrderInquirySuggestedLink).filter(
        OrderInquirySuggestedLink.po_line_id == po_line.id
    ).all():
        assert Decimal(str(suggested.qty)) > 0
