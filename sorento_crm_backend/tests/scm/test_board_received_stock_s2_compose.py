"""S2, compose never re-deals a received document (D1, R1).

`documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` S2, UAC
`board-received-stock-own-arrival-acceptance-criteria.md` AC-S2-1 to AC-S2-3. RED before the
coder's slice lands - no implementation to look at, testing the CONTRACT: `_placed_links`
(`planning_change_service.py` ~:1442) returns `qty` (unchanged - the total already linked,
for arrival/late maths) plus TWO NEW keys, `po_qty` (open purchase-order-line quantity still
reallocatable) and `received_qty` (link qty on received PO lines + all SPO allocation links
judged received), and `compose_suggestion` reads `po_qty` wherever it reads "what is placed
and could be reallocated" today, composing `received_qty` as a `keep` component labelled
"Received {document} {qty}" instead - never a `reallocate`.

CONTRACT CHOICES this file pins, because the plan leaves the exact shape open:
- `_placed_links` returns a `dict` (as it does today), simply gaining the two keys - not a
  new type. AC-S2-1 asserts the three keys directly.
- `compose_suggestion` is exercised as the PURE function it is documented to be ("No I/O,
  no clock, no database" - its own docstring) - `facts["placed"]` is built by hand with the
  three keys AC-S2-2/AC-S2-3 name, rather than driven through a live board/ladder walk. This
  is the simplest thing that proves the composition rule without a second, heavier fixture
  family only S3 actually needs.

`_placed_links` itself (AC-S2-1) IS run against a real Postgres chain - a real
`OrderInquiryRow` linked to a real, fully-received `SPOAllocation` - because that seam does
touch the database.

Fixtures imported rather than copied: `tests.test_planning_changes` (`api`, `_core_so`,
`_core_line`, `_project_so`, `_project_line`, `_uid`). Postgres only, every FK seeded here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import IV_ORDER, INQUIRY_PLACED, OrderInquiry, OrderInquiryLink, OrderInquiryRow
from app.services import planning_change_service

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    api,
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _uid,
)


def _received_spo(db, world, *, qty, po_number=None):
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=_uid(), spo_number=po_number or f"ZZT-SPO-{_uid()[:8]}", spo_line_number=1,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        allocated_quantity=int(qty), quantity_received=int(qty),
        receipt_status="fully_received", line_status="closed",
        from_po_number=f"ZZT-PO-{_uid()[:8]}",
    )
    db.add(row)
    db.flush()
    return row


def _open_po_line(db, world, *, qty):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier

    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name="zzt-s2compose supplier",
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
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    return po, po_line


def _raise_row_and_link_spo(db, world, line, *, qty, spo):
    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=line.project_sales_order_id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal(str(qty)), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(row)
    db.flush()
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id,
        spo_allocation_id=spo.id, document=spo.spo_number, qty=Decimal(str(qty)),
    )
    db.add(link)
    db.commit()
    return row, link


def test_ac_s2_1_placed_links_splits_open_po_qty_from_received_qty(api):
    """AC-S2-1: "`_placed_links` on a line whose only links are received SPO allocations
    returns `po_qty = 0`, `received_qty = linked total`, `qty = linked total`."
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2027, 6, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    spo = _received_spo(db, world, qty="40")
    _raise_row_and_link_spo(db, world, line, qty="40", spo=spo)

    placed = planning_change_service._placed_links(db, str(line.id))

    assert placed.get("po_qty") == "0", placed
    assert placed.get("received_qty") == "40", placed
    assert placed.get("qty") == "40", placed


def test_ac_s2_2_an_undecided_line_with_a_received_link_composes_keep_never_reallocate(api):
    """AC-S2-2: "`compose_suggestion` for an undecided delayed line with `received_qty =
    40`, `po_qty = 0` and a fresh answer that buys 2: no `reallocate` component; a `keep`
    component labelled "Received {document} 40"."

    `held=None` (nobody has decided this line yet) and a `proposal` that buys 2, the
    undecided-line compose path (`compose_suggestion` ~:665-678 today, reading
    `placed_qty` off the OLD single `qty` key) is what this exercises: an undecided line
    can still have quantity on a document (review round D2), and the received half of it
    must never be offered back to `reallocate_to`.
    """
    facts = {
        "placed": {
            "qty": "40", "po_qty": "0", "received_qty": "40", "document": "ZZT-SPO-0001",
            "arrival_date": None,
        },
        "reallocate_to": "pool",
        "new_date": date(2027, 6, 1).isoformat(),
        "immediate": False,
    }
    proposal = {
        "sources": [{"kind": "buy", "qty": "2"}],
        "qty_proposed_buy": "2",
    }
    suggestion = planning_change_service.compose_suggestion("delayed", None, proposal, facts)

    components = suggestion["components"]
    assert not any(c["action"] == "reallocate" for c in components), components
    keep = next((c for c in components if c["action"] == "keep"), None)
    assert keep is not None, components
    assert keep["label"] == "Received ZZT-SPO-0001 40", keep


def test_ac_s2_3_an_open_po_share_beside_a_received_share_reallocates_only_the_open_part(api):
    """AC-S2-3: "A line with an open (unreceived) PO link of 30 and a received link of 40,
    delayed beyond the window: the reallocate component is for 30 (the open part) only."

    `held` carries a Buy of 70 (30 open + 40 received - the OLD single `qty` this line's
    hold was built against), and `_document_outstays_the_window` fires (rule 7): the whole
    Buy is normally reallocated whole and re-bought for the new date. With `po_qty` in
    play the reallocated amount must be exactly the OPEN 30 - the received 40 is never
    offered to `reallocate_to` a second time.
    """
    facts = {
        "placed": {
            "qty": "70", "po_qty": "30", "received_qty": "40", "document": "ZZT-PO-0002",
            "arrival_date": date(2026, 1, 1).isoformat(),
        },
        "reallocate_to": "pool",
        "new_date": date(2027, 6, 1).isoformat(),
        "immediate": False,
    }
    held = {"buy_qty": "70"}
    proposal = {
        "sources": [{"kind": "buy", "qty": "70"}],
        "qty_proposed_buy": "70",
    }
    suggestion = planning_change_service.compose_suggestion("delayed", held, proposal, facts)

    components = suggestion["components"]
    reallocate = next((c for c in components if c["action"] == "reallocate"), None)
    assert reallocate is not None, components
    assert reallocate["qty_now"] == "30", reallocate
