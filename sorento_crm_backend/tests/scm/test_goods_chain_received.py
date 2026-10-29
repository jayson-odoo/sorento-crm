"""LINKAGE-UNIFY U2 (PLAN-linkage-unify-26oct section 8): received semantics, GR bins and
dead hops of `app.services.scm.goods_chain`. AC-R3..AC-R7 at chain level.

Seeded Goods Received (the shapes `procurement_service.get_received_quantities_by_product`
counts: `picking_type = 'goods_received'` and `picking_status = 'approved'`; `is_cancelled`
stays at its default false):

* AutoCount GR: header `doc_key` set (unique per test), line `qty` = the quantity, line
  `location_code` = the bin's warehouse code, link by `po_line_id` or `spo_allocation_id`.
* Excel GR: header `doc_key` NULL, header `spo_number` = the PO number, line `qty` NULL,
  `quantity_picked` = the quantity, bin only in `source_warehouse_id`, no line link.

Every chain is seeded here; nothing is borrowed.
"""
from __future__ import annotations

import importlib
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_goods_chain import T0, _World
from tests.scm.test_stock_debt_routes import _u

pytestmark = requires_pg

TODAY = date.today()
D1 = date(2026, 9, 1)
D2 = date(2026, 9, 5)


def _gc():
    return importlib.import_module("app.services.scm.goods_chain")


# ---------------------------------------------------------------------------- GR seeding


def _gr_header(db, *, doc_key, spo_number, picking_date, status="approved"):
    from app.models.procurement import PickingHeader

    header = PickingHeader(
        id=_u(),
        picking_number=f"ZZTGR-{_u()[:10]}",
        spo_number=spo_number,
        picking_type="goods_received",
        picking_status=status,
        picking_date=picking_date,
        doc_key=doc_key,
        source_book="AED_SORENTO" if doc_key is not None else None,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(header)
    db.flush()
    return header


_AUTO = object()


def gr_autocount(db, w, *, qty, bin_code, picking_date, po_line=None, spo=None,
                 destination=_AUTO, status="approved"):
    """An AutoCount GR line naming a PO line or an SPO allocation, received at `bin_code`.
    The ingest resolves the bin to `destination_warehouse_id` (the id the chain reads);
    `destination` defaults to the warehouse whose code is `bin_code` (None when no such
    warehouse), pass an id or None to override."""
    from app.models.inventory import Warehouse
    from app.models.procurement import PickingLine

    if destination is _AUTO:
        destination = (
            db.query(Warehouse.id).filter(Warehouse.warehouse_code == bin_code).scalar()
        )

    header = _gr_header(
        db, doc_key=random.randint(10**8, 10**12), picking_date=picking_date,
        spo_number=spo.spo_number if spo is not None else None, status=status,
    )
    line = PickingLine(
        id=_u(),
        picking_header_id=header.id,
        product_id=w.product.id,
        quantity_expected=int(qty),
        quantity_picked=int(qty),
        qty=Decimal(str(qty)),
        location_code=bin_code,
        destination_warehouse_id=destination,
        po_line_id=po_line.id if po_line is not None else None,
        spo_allocation_id=spo.id if spo is not None else None,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(line)
    db.flush()
    return line


def gr_excel(db, w, *, qty, bin_row, picking_date, po_number, spo=None, po_line=None):
    """An Excel GR line: no doc_key, no `qty`; the PO number sits in the header
    `spo_number`, the bin only in `source_warehouse_id`. `spo` / `po_line` set the line's
    own link columns (default: no line link)."""
    from app.models.procurement import PickingLine

    header = _gr_header(db, doc_key=None, spo_number=po_number, picking_date=picking_date)
    line = PickingLine(
        id=_u(),
        picking_header_id=header.id,
        product_id=w.product.id,
        quantity_expected=int(qty),
        quantity_picked=int(qty),
        qty=None,
        source_warehouse_id=bin_row.id,
        spo_allocation_id=spo.id if spo is not None else None,
        po_line_id=po_line.id if po_line is not None else None,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(line)
    db.flush()
    return line


# ---------------------------------------------------------------------------- helpers


def _view(chain):
    """(kind, state, qty, bin code, reason) per hop."""
    return [
        (h.kind, h.state, Decimal(str(h.qty)), h.warehouse_code, h.reason)
        for h in chain.hops
    ]


def _chain(db, link):
    out = _gc().chains_for_links(db, [str(link.id)])
    assert str(link.id) in out
    return out[str(link.id)]


def _landed_spo(w, po, po_line, *, qty, bin_row=None):
    spo = w.onto(
        po, po_line, qty=qty, received=qty, status="fully_received", line_status="closed",
        arrives=TODAY - timedelta(days=5), warehouse=bin_row,
    )
    return spo


# ---------------------------------------------------------------------------- seed check


def test_seed_gr_builds(scm_app):
    """Seeding only (passes today): both GR shapes land as described."""
    from app.models.procurement import PickingHeader, PickingLine

    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    ac = gr_autocount(db, w, qty=30, bin_code=w.b1.warehouse_code, picking_date=D1,
                      po_line=po_line)
    ex = gr_excel(db, w, qty=70, bin_row=w.b2, picking_date=D2, po_number=po.po_number)
    a = db.get(PickingLine, ac.id)
    b = db.get(PickingLine, ex.id)
    assert a.qty == Decimal("30") and a.po_line_id == po_line.id and a.location_code
    assert b.qty is None and b.source_warehouse_id == w.b2.id and b.po_line_id is None
    ha = db.get(PickingHeader, a.picking_header_id)
    hb = db.get(PickingHeader, b.picking_header_id)
    assert (ha.picking_type, ha.picking_status) == ("goods_received", "approved")
    assert ha.doc_key is not None and hb.doc_key is None and hb.spo_number == po.po_number


# ---------------------------------------------------------------------------- AC-R3..R5


def test_ac_r3_po_received_no_spo_gr_known(scm_app):
    """PO line 100 closed, 100 transferred, no SPO names it; GR lines naming the PO line: 30
    at B1 (1 Sep), 70 at B2 (5 Sep); placement 50 -> received_direct 30 at B1 + 20 at B2."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_autocount(db, w, qty=70, bin_code=w.b2.warehouse_code, picking_date=D2, po_line=po_line)
    gr_autocount(db, w, qty=30, bin_code=w.b1.warehouse_code, picking_date=D1, po_line=po_line)
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [
        ("po", "received_direct", Decimal("30"), w.b1.warehouse_code, None),
        ("po", "received_direct", Decimal("20"), w.b2.warehouse_code, None),
    ]
    assert chain.unplaced_qty == Decimal("0")


def test_ac_r3_gr_capacity_goes_to_placements_in_linked_at_order(scm_app):
    """Two placements share the GR lines in `linked_at, id` order: P1 25 takes B1's 30
    (25), P2 25 takes B1's last 5 then 20 at B2."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_autocount(db, w, qty=30, bin_code=w.b1.warehouse_code, picking_date=D1, po_line=po_line)
    gr_autocount(db, w, qty=70, bin_code=w.b2.warehouse_code, picking_date=D2, po_line=po_line)
    _r1, p1 = w.place_on_po(po_line, 25, minute=1)
    _r2, p2 = w.place_on_po(po_line, 25, minute=2)
    out = _gc().chains_for_links(db, [str(p1.id), str(p2.id)])
    assert _view(out[str(p1.id)]) == [
        ("po", "received_direct", Decimal("25"), w.b1.warehouse_code, None)
    ]
    assert _view(out[str(p2.id)]) == [
        ("po", "received_direct", Decimal("5"), w.b1.warehouse_code, None),
        ("po", "received_direct", Decimal("20"), w.b2.warehouse_code, None),
    ]


def test_ac_r4_po_received_no_spo_no_gr(scm_app):
    """As R3 with no GR line: received_direct 50 at the PO line's own bin."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [
        ("po", "received_direct", Decimal("50"), w.b1.warehouse_code, None)
    ]
    assert chain.hops[0].po_line_id == str(po_line.id)
    assert chain.unplaced_qty == Decimal("0")


def test_ac_r5_excel_gr_counts_when_the_po_has_one_line_of_the_product(scm_app):
    """Excel GR (no doc_key, header spo_number = PO number, bin in source_warehouse_id,
    qty in quantity_picked): 30 at B1 + 70 at B2, one PO line of the product -> counts."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_excel(db, w, qty=30, bin_row=w.b1, picking_date=D1, po_number=po.po_number)
    gr_excel(db, w, qty=70, bin_row=w.b2, picking_date=D2, po_number=po.po_number)
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("po", "received_direct", Decimal("30"), w.b1.warehouse_code, None),
        ("po", "received_direct", Decimal("20"), w.b2.warehouse_code, None),
    ]


def test_ac_r5_excel_gr_does_not_count_when_the_po_has_two_lines_of_the_product(scm_app):
    """Two lines of the product on that PO: the Excel GR cannot say which, so it does not
    count and the answer falls back to R4 (the line's own bin B1, not the GR's B2)."""
    from app.models.procurement import PurchaseOrderLine

    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=w.product.id, warehouse_id=w.b1.id,
        qty_ordered=Decimal("10"), qty_received=Decimal("10"), line_status="closed",
        source_ref=f"ZZT:{_u()[:8]}:{_u()[:8]}", company_id=SORENTO_COMPANY_ID,
    ))
    db.flush()
    gr_excel(db, w, qty=100, bin_row=w.b2, picking_date=D1, po_number=po.po_number)
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("po", "received_direct", Decimal("50"), w.b1.warehouse_code, None)
    ]


# ---------------------------------------------------------------------------- AC-R6 dead


def test_ac_r6_dead_po_line_cancelled_with_nothing_transferred(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=0, open_line=False)
    po_line.line_status = "cancelled"
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("po", "dead", Decimal("0"), None, "po_cancelled")]
    assert chain.unplaced_qty == Decimal("50")


def test_ac_r6_dead_cancel_po_line(scm_app):
    """A Cancel PO: `qty_cancelled = qty_received`, nothing under the key."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    po_line.qty_cancelled = Decimal("100")
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("po", "dead", Decimal("0"), None, "po_cancelled")]
    assert chain.unplaced_qty == Decimal("50")


def test_ac_r6_dead_spo_line_retired_with_nothing_received(scm_app):
    from app.models.procurement import SPOAllocation  # noqa: F401
    from tests.scm.test_stock_debt_routes import _spo

    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    a.retired_at = datetime.utcnow()
    db.flush()
    _row, link = w.place_on_spo(a, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("spo", "dead", Decimal("0"), None, "spo_withdrawn")]
    assert chain.unplaced_qty == Decimal("50")


def test_ac_r6_dead_spo_line_closed_with_nothing_landed(scm_app):
    from tests.scm.test_stock_debt_routes import _spo

    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due, line_status="closed")
    _row, link = w.place_on_spo(a, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("spo", "dead", Decimal("0"), None, "spo_withdrawn")]
    assert chain.unplaced_qty == Decimal("50")


# ---------------------------------------------------------------------------- AC-R7 / Q6


def test_ac_r7_spo_receipt_hop_sits_at_the_gr_bin_not_the_spo_bin(scm_app):
    """SPO A received 260, SPO bin B1, the GR line naming A received 260 at B2: the hop is
    `received` at B2 (OI-2609-0352 L1216: SPO BRW-BB, GR at MWH)."""
    from tests.scm.test_stock_debt_routes import _spo

    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=260, arrives=TODAY - timedelta(days=5), received=260,
             receipt_status="fully_received", line_status="closed")
    gr_autocount(db, w, qty=260, bin_code=w.b2.warehouse_code, picking_date=D1, spo=a)
    _row, link = w.place_on_spo(a, 260)
    chain = _chain(db, link)
    assert _view(chain) == [("spo", "received", Decimal("260"), w.b2.warehouse_code, None)]
    assert chain.hops[0].warehouse_id == str(w.b2.id)
    assert chain.hops[0].spo_allocation_id == str(a.id)


def test_ac_r7_a_po_placement_following_a_received_spo_also_takes_the_gr_bin(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = _landed_spo(w, po, po_line, qty=100)
    gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code, picking_date=D1, spo=a)
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("spo", "received", Decimal("50"), w.b2.warehouse_code, None)
    ]


def test_landed_qty_no_gr_covers_stays_at_the_spo_bin(scm_app):
    """SPO landed 100 at B1, the GR names only 40 at B2: 40 at B2 then 60 at the SPO bin."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = _landed_spo(w, po, po_line, qty=100)
    gr_autocount(db, w, qty=40, bin_code=w.b2.warehouse_code, picking_date=D1, spo=a)
    _row, link = w.place_on_po(po_line, 100)
    assert _view(_chain(db, link)) == [
        ("spo", "received", Decimal("40"), w.b2.warehouse_code, None),
        ("spo", "received", Decimal("60"), w.b1.warehouse_code, None),
    ]


def test_a_gr_with_no_destination_warehouse_falls_back_to_the_document_bin(scm_app):
    """`destination_warehouse_id` NULL (the ingest could not resolve the code): the hop sits
    at the SPO's own bin, even though `location_code` happens to name another warehouse."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = _landed_spo(w, po, po_line, qty=100)
    gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code, picking_date=D1, spo=a,
                 destination=None)
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("spo", "received", Decimal("50"), w.b1.warehouse_code, None)
    ]


def test_r_c_the_gr_bin_is_destination_warehouse_id_not_the_location_code_text(scm_app):
    """`location_code` is a different-case, unknown code; `destination_warehouse_id` is B2
    (resolved at ingest): the hop sits at B2."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = _landed_spo(w, po, po_line, qty=100)
    gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code.lower() + "-x",
                 picking_date=D1, spo=a, destination=w.b2.id)
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("spo", "received", Decimal("50"), w.b2.warehouse_code, None)]
    assert chain.hops[0].warehouse_id == str(w.b2.id)


# ---------------------------------------------------------------------------- helpers


def test_is_received_and_received_qty_on_mixed_and_whole_chains(scm_app):
    """100 on the PO line: SPO A landed 40 (received), SPO B 60 in transit. The placement of
    100 is part received, part in transit -> not received, received_qty 40. A placement of 30
    lies wholly on A's landed goods -> received, 30. A dead chain is not received, 0."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    _landed_spo(w, po, po_line, qty=40)
    w.onto(po, po_line, qty=60, arrives=w.due)
    _r1, mixed = w.place_on_po(po_line, 100, minute=1)
    gc = _gc()
    chain = _chain(db, mixed)
    assert gc.is_received(chain) is False
    assert Decimal(str(gc.received_qty(chain))) == Decimal("40")

    w2 = _World(db)
    po2, po_line2 = w2.po(ordered=100, transferred=100)
    _landed_spo(w2, po2, po_line2, qty=100)
    _r2, whole = w2.place_on_po(po_line2, 30)
    whole_chain = _chain(db, whole)
    assert gc.is_received(whole_chain) is True
    assert Decimal(str(gc.received_qty(whole_chain))) == Decimal("30")

    w3 = _World(db)
    po3, po_line3 = w3.po(ordered=100, transferred=0, open_line=False)
    po_line3.line_status = "cancelled"
    db.flush()
    _r3, dead = w3.place_on_po(po_line3, 50)
    dead_chain = _chain(db, dead)
    assert gc.is_received(dead_chain) is False
    assert Decimal(str(gc.received_qty(dead_chain))) == Decimal("0")


def test_is_received_counts_received_direct_and_requires_nothing_unplaced(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    _r, link = w.place_on_po(po_line, 50)
    gc = _gc()
    chain = _chain(db, link)
    assert gc.is_received(chain) is True
    assert Decimal(str(gc.received_qty(chain))) == Decimal("50")
    # Placed past what the line transferred: 50 unplaced, so not wholly received.
    _r2, over = w.place_on_po(po_line, 80, minute=9)
    over_chain = _chain(db, over)
    assert over_chain.unplaced_qty > 0
    assert gc.is_received(over_chain) is False


# ---------------------------------------------------------------------------- U2 review round


def test_r_a_partial_cancel_po_on_an_open_line_is_still_on_order(scm_app):
    """PO line 100, Cancel PO took 40 (`qty_received` 40, `qty_cancelled` 40), line still
    open, no SPO: the 60 left is on order, so a placement of 50 is one `po` on_order hop,
    never dead."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=40)
    po_line.qty_cancelled = Decimal("40")
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert [(h.kind, h.state, Decimal(str(h.qty)), h.reason) for h in chain.hops] == [
        ("po", "on_order", Decimal("50"), None)
    ]
    assert chain.unplaced_qty == Decimal("0")


def test_r_b_a_crm_raised_spo_linked_by_po_line_fk_is_followed(scm_app):
    """An SPO allocation whose `po_line_id` is the PO line (no from_po_number /
    from_po_line_ref), PO line transferred 100, SPO 100 in transit at B2: the placement is
    one `spo` in_transit hop on that SPO, not received_direct at the PO bin."""
    from tests.scm.test_stock_debt_routes import _spo

    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = _spo(db, w.product, w.b2, qty=100, arrives=w.due)
    a.po_line_id = po_line.id
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert [(h.kind, h.state, Decimal(str(h.qty)), h.spo_number) for h in chain.hops] == [
        ("spo", "in_transit", Decimal("50"), a.spo_number)
    ]


def test_g1_a_gr_that_is_not_approved_does_not_count(scm_app):
    """A draft GR names the PO line with 100 at B2: it counts for no bin and no quantity, so
    the answer is R4's (50 at the PO line's own bin B1)."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code, picking_date=D1,
                 po_line=po_line, status="draft")
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("po", "received_direct", Decimal("50"), w.b1.warehouse_code, None)
    ]


def test_g2_an_excel_gr_line_naming_an_spo_is_not_also_counted_against_the_po(scm_app):
    """Excel header `spo_number` = the PO number, but the line carries `spo_allocation_id`
    of another SPO (30 at B3, earliest): it belongs to that SPO, not to the PO line. The
    PO line's received_direct is the unlinked Excel line (70 at B2) then the uncovered 30 at
    the PO bin B1; the 30 at B3 is not double counted."""
    from tests.scm.test_stock_debt_routes import _spo, _warehouse

    db = scm_app[1]
    w = _World(db)
    b3 = _warehouse(db, f"ZZTB3{_u()[:4]}")
    po, po_line = w.po(ordered=100, transferred=100)
    other = _spo(db, w.product, b3, qty=30, arrives=TODAY - timedelta(days=3), received=30,
                 receipt_status="fully_received", line_status="closed")
    gr_excel(db, w, qty=30, bin_row=b3, picking_date=D1, po_number=po.po_number, spo=other)
    gr_excel(db, w, qty=70, bin_row=w.b2, picking_date=D2, po_number=po.po_number)
    _row, link = w.place_on_po(po_line, 100)
    assert _view(_chain(db, link)) == [
        ("po", "received_direct", Decimal("70"), w.b2.warehouse_code, None),
        ("po", "received_direct", Decimal("30"), w.b1.warehouse_code, None),
    ]


def test_g3_a_cancelled_po_header_with_nothing_under_the_key_is_dead(scm_app):
    """PO header cancelled, line not on order, nothing transferred, no SPO: dead."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=0)
    po.status = "cancelled"
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _view(chain) == [("po", "dead", Decimal("0"), None, "po_cancelled")]
    assert chain.unplaced_qty == Decimal("50")


def test_g4_an_excel_style_gr_line_with_a_po_line_id_is_not_an_autocount_po_gr(scm_app):
    """Only a header with `doc_key` links a PO line by `po_line_id`. This GR header has no
    doc_key (and its `spo_number` is not the PO number, so the Excel route misses it too):
    it does not count, and the answer is R4's (50 at the PO line's own bin B1)."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_excel(db, w, qty=100, bin_row=w.b2, picking_date=D1, po_number=f"NOT-{po.po_number}",
             po_line=po_line)
    _row, link = w.place_on_po(po_line, 50)
    assert _view(_chain(db, link)) == [
        ("po", "received_direct", Decimal("50"), w.b1.warehouse_code, None)
    ]
