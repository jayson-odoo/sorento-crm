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


def _open_spo(db, world, *, qty, spo_number=None):
    """An SPO allocation the goods have NOT arrived against yet: `receipt_status` outside
    `spo_supply.RECEIVED_RECEIPT_STATUSES`, `line_status` still `open` -
    `_received_documents_for`'s own `is_open` test (`project_order_inquiry_service.py`
    ~:1817-1827) reads this as open, so a link naming it is never counted into
    `received_qty` - AC-S2-4/AC-S2-5's own point is that it must ALSO never be counted into
    `po_qty`, because `_document_links_by_row` (planning_change_service.py ~:2996) can only
    re-deal a link that carries a `po_line_id`, never one that only carries an
    `spo_allocation_id`.
    """
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=_uid(), spo_number=spo_number or f"ZZT-SPO-{_uid()[:8]}", spo_line_number=1,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        allocated_quantity=int(qty), quantity_received=0,
        receipt_status="pending", line_status="open",
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


def _raise_row_and_link_po(db, world, line, *, qty, po_line, document):
    """Same shape as `_raise_row_and_link_spo`, but the link carries `po_line_id` instead
    of `spo_allocation_id` - the only kind `_document_links_by_row` can re-deal.
    """
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
        po_line_id=po_line.id, document=document, qty=Decimal(str(qty)),
    )
    db.add(link)
    db.commit()
    return row, link


def _raise_po_and_spo_rows_on_one_inquiry(
    db, world, line, *, po_qty, po_line, po_document, spo_qty, spo,
):
    """Two `OrderInquiryRow`s, one link each (PO, then SPO), sharing a SINGLE
    `OrderInquiry` - `order_inquiries` carries `uq_project_order_inquiry_per_sales_order`
    (one inquiry per Project SO), so `_raise_row_and_link_po` /
    `_raise_row_and_link_spo`'s own each-call-makes-an-inquiry shape (fine when a test
    calls only one of them) cannot be called twice against the SAME line - AC-S2-4/AC-S2-5
    need both a PO link and an SPO link on the one line at once.

    The PO row/link is created FIRST (earlier `linked_at`), so `_placed_links`'s own
    `document = next(link.document for link in links if link.document)` already names the
    PO even under today's bug.
    """
    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=line.project_sales_order_id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()

    po_row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal(str(po_qty)), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(po_row)
    db.flush()
    po_link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=po_row.id,
        po_line_id=po_line.id, document=po_document, qty=Decimal(str(po_qty)),
    )
    db.add(po_link)
    db.commit()

    spo_row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal(str(spo_qty)), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(spo_row)
    db.flush()
    spo_link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=spo_row.id,
        spo_allocation_id=spo.id, document=spo.spo_number, qty=Decimal(str(spo_qty)),
    )
    db.add(spo_link)
    db.commit()

    return (po_row, po_link), (spo_row, spo_link)


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


# --------------------------------------------------------------------------- #
# Phase 3 fix-round reds (SF12) - `po_qty` must exclude an OPEN SPO allocation #
# link (only a `po_line_id` link is something `_document_links_by_row` can    #
# ever re-deal), added to S2 21 Sep evening                                    #
# --------------------------------------------------------------------------- #


def test_ac_s2_4_po_qty_excludes_open_spo_allocation_links(api):
    """AC-S2-4 (Phase 3 fix round, SF12). `_placed_links` on a line with an OPEN (not
    received) SPO allocation link of 30 (`po_line_id` NULL, `receipt_status` not
    `fully_received`) and an open purchase-order-line link of 20 (`po_line_id` set) must
    return `po_qty = 20` - only what `_document_links_by_row`
    (`planning_change_service.py` ~:2996) can actually re-deal (it filters
    `OrderInquiryLink.po_line_id.isnot(None)`, so an SPO-only link is never a candidate for
    reallocation no matter how open it is) - `received_qty = 0` (the SPO has not arrived,
    `_received_documents_for`'s own `is_open` test excludes it from `received` too), and
    `qty = 50` (the sum, unchanged, for arrival/late maths).

    RED today: `_placed_links` computes `po_qty = total - received_qty`
    (`planning_change_service.py` ~:1502), which folds an OPEN SPO allocation link into
    `po_qty` merely because it is not RECEIVED - it never checks that the link is one
    `_document_links_by_row` can actually spend. Expect `po_qty == "50"` today (30 open SPO
    + 20 open PO), not the "20" this test pins.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50",
                            required_date=date(2027, 6, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po, po_line = _open_po_line(db, world, qty=20)
    spo = _open_spo(db, world, qty=30)
    _raise_po_and_spo_rows_on_one_inquiry(
        db, world, line, po_qty=20, po_line=po_line, po_document=po.po_number,
        spo_qty=30, spo=spo,
    )

    placed = planning_change_service._placed_links(db, str(line.id))

    assert placed.get("po_qty") == "20", placed
    assert placed.get("received_qty") == "0", placed
    assert placed.get("qty") == "50", placed


def test_ac_s2_5_compose_never_reallocates_an_open_spo_allocation(api):
    """AC-S2-5 (Phase 3 fix round, SF12). With AC-S2-4's own shape - a line whose OPEN
    reallocatable quantity is `po_qty = 20` (the open PO line; the open SPO allocation's 30
    excluded) - `compose_suggestion` for an undecided delayed line (`held=None`, the same
    undecided path AC-S2-2 exercises) composes a `reallocate` for 20 ONLY, naming the PO's
    OWN document, never the SPO's: the open SPO allocation carries no `po_line_id`
    `_document_links_by_row` could later spend, so offering its 30 up via `reallocate_to`
    would promise a document Confirm can never actually re-deal.

    Facts are read off the REAL `_placed_links(db, line.id)` this test's own DB chain
    produces (unlike AC-S2-2/AC-S2-3's hand-built facts) - the point proved here is the
    END-TO-END chain from the real bug in `_placed_links` through to what the board would
    compose, not an isolated `compose_suggestion` unit already handed the corrected number.

    RED today: `_placed_links` folds the open SPO's 30 into `po_qty` (AC-S2-4), so
    `compose_suggestion` reads `placed_qty = 50` here (the buggy `po_qty`) and composes a
    reallocate of 50 (`spare = placed_qty - proposed_buy_qty = 50 - 0`), not the 20 this
    test pins.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50",
                            required_date=date(2027, 6, 1))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po, po_line = _open_po_line(db, world, qty=20)
    spo = _open_spo(db, world, qty=30)
    _raise_po_and_spo_rows_on_one_inquiry(
        db, world, line, po_qty=20, po_line=po_line, po_document=po.po_number,
        spo_qty=30, spo=spo,
    )

    placed = planning_change_service._placed_links(db, str(line.id))
    facts = {
        "placed": placed,
        "reallocate_to": "pool",
        "new_date": date(2027, 6, 1).isoformat(),
        "immediate": False,
    }
    proposal = {
        "sources": [],
        "qty_proposed_buy": "0",
    }
    suggestion = planning_change_service.compose_suggestion("delayed", None, proposal, facts)

    components = suggestion["components"]
    reallocate = next((c for c in components if c["action"] == "reallocate"), None)
    assert reallocate is not None, components
    assert reallocate["qty_now"] == "20", reallocate
    assert reallocate.get("document") == po.po_number, reallocate
    assert reallocate.get("document") != spo.spo_number, reallocate
