"""LINKAGE-UNIFY U2 (PLAN section 8, call sites 1-3): the OI "received" answer follows the
goods chain. AC-R1, AC-R2, AC-R6, AC-R8.

Readers under test, on `ProjectOrderInquiryService` (#973 OI-REPLAN-RECEIVED-LINKS, #1708
OI-RESERVE-RECEIVED): `links_for_rows` (`received`, `received_qty`),
`_received_documents_for`, `received_links_of`, `po_lines_with_open_chained_spo`.
Seeding is `test_goods_chain._World`: a PO line transferred onto an SPO, a placement on the
PO line, every row seeded here.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from tests.scm.conftest import requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_goods_chain_received import TODAY
from tests.scm.test_stock_debt_routes import _spo

pytestmark = requires_pg


def _entry(svc, row, link):
    [entry] = [e for e in svc.links_for_rows([str(row.id)])[str(row.id)] if e["id"] == link.id]
    return entry


def _in_transit_placement(db):
    """AC-R1's chain: PO line 100 closed, 100 transferred onto SPO A (100, 0 received,
    open, no arrival); placement 50 on the PO line."""
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100)
    row, link = w.place_on_po(po_line, 50)
    return w, po, po_line, a, row, link


def _landed_placement(db):
    """AC-R2's chain: as above with SPO A 100/100 fully_received and closed."""
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100, received=100, status="fully_received",
               line_status="closed", arrives=TODAY - timedelta(days=5))
    row, link = w.place_on_po(po_line, 50)
    return w, po, po_line, a, row, link


def test_seed_oi_chain_builds(scm_app):
    """Seeding only (passes today): the row serves its link on the wire."""
    db = scm_app[1]
    _w, _po, po_line, _a, row, link = _in_transit_placement(db)
    entry = _entry(ProjectOrderInquiryService(db), row, link)
    assert entry["kind"] == "po" and entry["po_line_id"] == str(po_line.id)


def test_ac_r1_in_transit_is_not_received(scm_app):
    db = scm_app[1]
    _w, _po, _line, _a, row, link = _in_transit_placement(db)
    svc = ProjectOrderInquiryService(db)
    assert _entry(svc, row, link)["received"] is False
    assert str(link.id) not in svc._received_documents_for([link])
    assert svc.received_links_of(str(row.id)) == []


def test_ac_r2_landed_is_received_with_the_placements_share(scm_app):
    db = scm_app[1]
    _w, _po, _line, a, row, link = _landed_placement(db)
    svc = ProjectOrderInquiryService(db)
    entry = _entry(svc, row, link)
    assert entry["received"] is True
    assert Decimal(str(entry["received_qty"])) == Decimal("50")
    assert str(link.id) in svc._received_documents_for([link])
    assert [str(x.id) for x in svc.received_links_of(str(row.id))] == [str(link.id)]


def test_ac_r2_received_qty_is_the_share_when_the_spo_is_only_part_landed(scm_app):
    """SPO A 100, landed 40 (receipt 40, closed): a placement of 50 is not wholly received
    (40 landed + 10 unplaced), so received False, and the wire quantity is the 40."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    w.onto(po, po_line, qty=40, received=40, status="fully_received", line_status="closed",
           arrives=TODAY - timedelta(days=5))
    row, link = w.place_on_po(po_line, 50)
    entry = _entry(ProjectOrderInquiryService(db), row, link)
    assert entry["received"] is False
    assert Decimal(str(entry["received_qty"])) == Decimal("40")


def test_ac_r6_a_cancel_po_link_is_not_received(scm_app):
    """Cancel PO: `qty_cancelled = qty_received`, closed, nothing under the key. The
    document reads received today; it is dead, so received False and not offered to a
    reserve or replan."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    po_line.qty_cancelled = Decimal("100")
    db.flush()
    row, link = w.place_on_po(po_line, 50)
    svc = ProjectOrderInquiryService(db)
    assert _entry(svc, row, link)["received"] is False
    assert str(link.id) not in svc._received_documents_for([link])
    assert svc.received_links_of(str(row.id)) == []


def test_ac_r6_an_spo_closed_with_nothing_landed_is_not_received(scm_app):
    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due, line_status="closed")
    row, link = w.place_on_spo(a, 50)
    svc = ProjectOrderInquiryService(db)
    assert _entry(svc, row, link)["received"] is False
    assert str(link.id) not in svc._received_documents_for([link])
    assert svc.received_links_of(str(row.id)) == []


def test_ac_r8_received_links_of_follows_a_space_padded_ref(scm_app):
    """The SPO names the PO line with padded spaces and is still in transit: the chain
    follows it, so the placement is not received. Today the untrimmed join misses the SPO,
    the closed PO line reads received, and `received_links_of` hands the link out."""
    db = scm_app[1]
    w, _po, po_line, a, row, link = _in_transit_placement(db)
    a.from_po_line_ref = f"  {po_line.source_ref} "
    db.flush()
    svc = ProjectOrderInquiryService(db)
    assert svc.received_links_of(str(row.id)) == []
    assert _entry(svc, row, link)["received"] is False


def test_ac_r8_po_lines_with_open_chained_spo_uses_the_same_key(scm_app):
    """Same padded ref, same answer in the chained-open-SPO reader: the PO line is named
    as having an open SPO chained from it."""
    db = scm_app[1]
    w, _po, po_line, a, _row, _link = _in_transit_placement(db)
    a.from_po_line_ref = f"  {po_line.source_ref} "
    db.flush()
    assert ProjectOrderInquiryService(db).po_lines_with_open_chained_spo(
        [str(po_line.id)]
    ) == {str(po_line.id)}
