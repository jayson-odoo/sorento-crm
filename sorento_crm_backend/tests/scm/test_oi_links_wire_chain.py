"""LINKAGE-UNIFY U3 (PLAN section 9): the `links_for_rows` wire carries the chain.

Every entry gains `receipts: [{qty, bin}]` (the chain's `received` hops on that SPO, or the
`received_direct` hops on that PO line: the placement's share, at the GR bin). Every real
link gains `dead_reason` (`po_cancelled` | `spo_withdrawn` | null); a direct link on a
retired SPO line with nothing received is listed, no longer dropped. A received SPO yields
its derived entry. The worklist filter `dead_document` returns exactly the rows holding a
link whose chain is dead for that reason.

Shapes after the real cases: L880 (PO transferred onto an SPO that landed, GR at the bin),
class d (PO received, no SPO, GR), Cancel PO / retired SPO. Every chain is seeded here; GR
seeding is `test_goods_chain_received`'s.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from tests.scm.conftest import requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_goods_chain_received import D1, D2, TODAY, gr_autocount
from tests.scm.test_stock_debt_routes import _spo

pytestmark = requires_pg


def _links(db, row):
    return ProjectOrderInquiryService(db).links_for_rows([str(row.id)])[str(row.id)]


def _real(entries, link):
    [entry] = [e for e in entries if e["id"] == link.id]
    return entry


def _receipts(entry):
    return [(Decimal(str(r["qty"])), r["bin"]) for r in entry["receipts"]]


def _l880(db, *, landed=True):
    """PO line 486 transferred onto SPO 486 (landed with a GR at B1, or still in transit)."""
    w = _World(db)
    po, po_line = w.po(ordered=486, transferred=486)
    if landed:
        a = w.onto(po, po_line, qty=486, received=486, status="fully_received",
                   line_status="closed", arrives=TODAY - timedelta(days=5))
        gr_autocount(db, w, qty=486, bin_code=w.b1.warehouse_code, picking_date=D1, spo=a)
    else:
        a = w.onto(po, po_line, qty=486)
    row, link = w.place_on_po(po_line, 486)
    return w, po, po_line, a, row, link


def test_seed_wire_chain_builds(scm_app):
    """Seeding only (passes today): the row is served and listed by the worklist service."""
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    db = scm_app[1]
    _w, _po, po_line, _a, row, link = _l880(db)
    assert _real(_links(db, row), link)["po_line_id"] == str(po_line.id)
    page = OrderInquiryWorklistService(db).list_rows(inquiry_id=str(row.order_inquiry_id))
    assert [r["id"] for r in page["data"]] == [str(row.id)]


# ---------------------------------------------------------------------------- receipts


def test_ac_d1_a_received_spo_yields_its_derived_entry_with_the_gr_receipt(scm_app):
    """L880: PO 486 onto SPO 486/486 received, GR at B1. The real PO entry has no receipts
    (no PO pill); the derived SPO entry exists and carries [{486, B1}]."""
    db = scm_app[1]
    w, po, _line, a, row, link = _l880(db)
    entries = _links(db, row)
    assert all("receipts" in e for e in entries)
    assert _real(entries, link)["receipts"] == []
    [spo_entry] = [e for e in entries if e["kind"] == "spo" and e["document"] == a.spo_number]
    assert spo_entry.get("derived") is True
    assert _receipts(spo_entry) == [(Decimal("486"), w.b1.warehouse_code)]


def test_ac_d1_an_in_transit_spo_derived_entry_has_no_receipts(scm_app):
    db = scm_app[1]
    w, po, _line, a, row, link = _l880(db, landed=False)
    entries = _links(db, row)
    [spo_entry] = [e for e in entries if e["kind"] == "spo" and e["document"] == a.spo_number]
    assert spo_entry["receipts"] == []
    assert _real(entries, link)["receipts"] == []


def test_ac_d1_class_d_po_entry_carries_the_gr_receipt(scm_app):
    """PO received, no SPO under the key, GR at B2: the PO entry itself carries
    [{qty, B2}] (the placement's share)."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code, picking_date=D1, po_line=po_line)
    row, link = w.place_on_po(po_line, 50)
    entry = _real(_links(db, row), link)
    assert _receipts(entry) == [(Decimal("50"), w.b2.warehouse_code)]


def test_ac_d1_a_gr_split_over_two_bins_gives_two_receipts(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    gr_autocount(db, w, qty=30, bin_code=w.b1.warehouse_code, picking_date=D1, po_line=po_line)
    gr_autocount(db, w, qty=70, bin_code=w.b2.warehouse_code, picking_date=D2, po_line=po_line)
    row, link = w.place_on_po(po_line, 50)
    entry = _real(_links(db, row), link)
    assert _receipts(entry) == [
        (Decimal("30"), w.b1.warehouse_code),
        (Decimal("20"), w.b2.warehouse_code),
    ]


# ---------------------------------------------------------------------------- dead_reason


def test_ac_d3_a_cancelled_po_line_link_says_po_cancelled(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=0, open_line=False)
    po_line.line_status = "cancelled"
    db.flush()
    row, link = w.place_on_po(po_line, 50)
    assert _real(_links(db, row), link)["dead_reason"] == "po_cancelled"


def test_ac_d3_a_link_on_a_retired_spo_with_nothing_received_is_listed_as_withdrawn(scm_app):
    """Today `visible_line_clauses` drops this link from the list; it is listed now, and
    says why it is dead."""
    from datetime import datetime

    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    a.retired_at = datetime.utcnow()
    db.flush()
    row, link = w.place_on_spo(a, 50)
    entry = _real(_links(db, row), link)
    assert entry["dead_reason"] == "spo_withdrawn"


def test_ac_d3_a_live_link_has_a_null_dead_reason(scm_app):
    db = scm_app[1]
    w, _po, _line, _a, row, link = _l880(db, landed=False)
    entry = _real(_links(db, row), link)
    assert "dead_reason" in entry
    assert entry["dead_reason"] is None


# ---------------------------------------------------------------------------- filter


def _dead_world(db):
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=0, open_line=False)
    po_line.line_status = "cancelled"
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    from datetime import datetime

    a.retired_at = datetime.utcnow()
    db.flush()
    po_row, _l1 = w.place_on_po(po_line, 50)
    spo_row, _l2 = w.place_on_spo(a, 50)
    live = _World(db)
    lpo, lline = live.po(ordered=100, transferred=0)
    live_row, _l3 = live.place_on_po(lline, 50)
    return str(po_row.id), str(spo_row.id), str(live_row.id)


def _ids(db, **filters):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    try:
        page = OrderInquiryWorklistService(db).list_rows(limit=200, **filters)
    except TypeError as exc:
        pytest.fail(f"list_rows takes no dead_document filter yet: {exc}")
    return {r["id"] for r in page["data"]}


def test_ac_d3_the_dead_document_filter_returns_exactly_the_rows_with_such_a_link(scm_app):
    db = scm_app[1]
    po_row, spo_row, live_row = _dead_world(db)
    cancelled = _ids(db, dead_document="po_cancelled")
    withdrawn = _ids(db, dead_document="spo_withdrawn")
    assert po_row in cancelled and spo_row not in cancelled and live_row not in cancelled
    assert spo_row in withdrawn and po_row not in withdrawn and live_row not in withdrawn
