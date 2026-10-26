"""LINKAGE-UNIFY U4 (PLAN section 12): the PO and SPO documents answer through the chain.

`goods_chain.placements_on` returns every live placement whose chain passes through given
documents, each with its `LinkChain`; a placement on a PO line that follows onto an SPO is
returned for that SPO with `via_po` = the PO number. The PO popup lines carry `spos`
(one entry per SPO line transferred onto: spo_number, line_label, receipts, dead_reason),
the SPO document's "SO covered" list the via-PO placements marked with `via_po`, and the SCM PO detail lines
carry the same `spos`.

Shape: PO line 100 transferred onto SPO A 100 (landed, GR at B2, line L12). P1 = 70 placed
on the PO line (follows onto A, via PO), P2 = 30 placed directly on A. Quantities differ so
each placement is told apart by its qty. Every chain is seeded here.
"""
from __future__ import annotations

import importlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from tests.scm.conftest import requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_goods_chain_received import D1, TODAY, gr_autocount

pytestmark = requires_pg


def _gc():
    return importlib.import_module("app.services.scm.goods_chain")


def _world(db, *, landed=True):
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    if landed:
        a = w.onto(po, po_line, qty=100, received=100, status="fully_received",
                   line_status="closed", arrives=TODAY - timedelta(days=5), warehouse=w.b1)
        gr_autocount(db, w, qty=100, bin_code=w.b2.warehouse_code, picking_date=D1, spo=a)
    else:
        a = w.onto(po, po_line, qty=100, warehouse=w.b1)
    a.spo_line_number = 12
    db.flush()
    row1, link1 = w.place_on_po(po_line, 70, minute=1)
    row2, link2 = w.place_on_spo(a, 30, minute=2)
    return SimpleNamespace(w=w, po=po, po_line=po_line, a=a, row1=row1, link1=link1,
                           row2=row2, link2=link2)


def _items(result):
    return list(result.values()) if isinstance(result, dict) else list(result)


def _chain_of(item):
    return getattr(item, "chain", item)


def _by_qty(entries, qty):
    return [e for e in entries if Decimal(str(e["qty"])) == Decimal(str(qty))]


def test_seed_documents_world_builds(scm_app):
    """Seeding only (passes today)."""
    db = scm_app[1]
    s = _world(db)
    assert s.link1.po_line_id == s.po_line.id and s.link2.spo_allocation_id == s.a.id


# ---------------------------------------------------------------------------- D1


def _placements_on():
    fn = getattr(_gc(), "placements_on", None)
    assert fn is not None, "goods_chain.placements_on is missing"
    return fn


def test_d1_placements_on_a_po_line_returns_its_placements_with_chains(scm_app):
    db = scm_app[1]
    s = _world(db)
    items = _items(_placements_on()(db, po_line_ids=[str(s.po_line.id)]))
    assert {_chain_of(i).link_id for i in items} == {str(s.link1.id)}
    chain = _chain_of(items[0])
    assert [(h.kind, h.state, Decimal(str(h.qty))) for h in chain.hops] == [
        ("spo", "received", Decimal("70"))
    ]


def test_d1_placements_on_an_spo_returns_direct_and_via_po_placements(scm_app):
    db = scm_app[1]
    s = _world(db)
    items = _items(_placements_on()(db, spo_allocation_ids=[str(s.a.id)]))
    via = {_chain_of(i).link_id: getattr(i, "via_po", None) for i in items}
    assert via == {str(s.link1.id): s.po.po_number, str(s.link2.id): None}


# ---------------------------------------------------------------------------- D2


def _svc(db):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    return OrderInquiryWorklistService(db)


def test_d2_po_detail_lines_carry_their_spos_with_receipts(scm_app):
    db = scm_app[1]
    s = _world(db)
    detail = _svc(db).get_po_detail(str(s.po.id))
    [line] = [ln for ln in detail["lines"] if ln["id"] == str(s.po_line.id)]
    spos = line.get("spos")
    assert spos is not None, sorted(line)
    [entry] = spos
    assert entry["spo_number"] == s.a.spo_number
    assert entry["line_label"] == "L12"
    assert [(Decimal(str(r["qty"])), r["bin"]) for r in entry["receipts"]] == [
        (Decimal("100"), s.w.b2.warehouse_code)
    ]
    assert entry["dead_reason"] is None


def test_d2_a_withdrawn_spo_shows_on_the_po_line_with_its_reason(scm_app):
    from datetime import datetime

    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100)
    a.retired_at = datetime.utcnow()
    db.flush()
    detail = _svc(db).get_po_detail(str(po.id))
    [line] = detail["lines"]
    assert [(e["spo_number"], e["dead_reason"]) for e in line.get("spos", [])] == [
        (a.spo_number, "spo_withdrawn")
    ]


# ---------------------------------------------------------------------------- D4


def test_d4_the_spo_document_so_covered_includes_the_via_po_placement(scm_app):
    from app.services.procurement_service import SPOAllocationService

    db = scm_app[1]
    s = _world(db)
    doc = SPOAllocationService(db).get_document(s.a.spo_number)
    covered = [c for line in doc.lines for c in (line.so_covered or [])]
    via = [c for c in covered if Decimal(str(c.qty)) == Decimal("70")]
    assert [getattr(c, "via_po", None) for c in via] == [s.po.po_number]
    direct = [c for c in covered if Decimal(str(c.qty)) == Decimal("30")]
    assert [getattr(c, "via_po", None) for c in direct] == [None]


# ---------------------------------------------------------------------------- D5


def test_d5_scm_po_detail_lines_carry_the_same_spos(scm_app):
    from app.services.scm.purchase_order_service import PurchaseOrderService

    db = scm_app[1]
    s = _world(db)
    detail = PurchaseOrderService(db).get_one(str(s.po.id))
    [line] = [ln for ln in detail["lines"] if str(ln["id"]) == str(s.po_line.id)]
    spos = line.get("spos")
    assert spos is not None, sorted(line)
    [entry] = spos
    assert entry["spo_number"] == s.a.spo_number
    assert entry["line_label"] == "L12"
    assert [(Decimal(str(r["qty"])), r["bin"]) for r in entry["receipts"]] == [
        (Decimal("100"), s.w.b2.warehouse_code)
    ]


# ---------------------------------------------------------------------------- U4 round 2


def test_k7_via_po_share_on_each_spo_is_the_chains_split(scm_app):
    """PO line 100 onto SPO A 60 (earlier) and SPO B 40, both in transit; P1 50 then P2 50 on
    the PO line. On A: P1 50 and P2 10 (both via the PO). On B: P2 40 only."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=60, arrives=w.due.replace(day=1), warehouse=w.b1)
    b = w.onto(po, po_line, qty=40, arrives=w.due.replace(day=9), warehouse=w.b1)
    _r1, p1 = w.place_on_po(po_line, 50, minute=1)
    _r2, p2 = w.place_on_po(po_line, 50, minute=2)

    def shares(spo):
        out = {}
        for item in _items(_placements_on()(db, spo_allocation_ids=[str(spo.id)])):
            chain = _chain_of(item)
            qty = sum(
                (Decimal(str(h.qty)) for h in chain.hops if h.spo_allocation_id == str(spo.id)),
                Decimal("0"),
            )
            out[chain.link_id] = (qty, getattr(item, "via_po", None))
        return out

    assert shares(a) == {
        str(p1.id): (Decimal("50"), po.po_number),
        str(p2.id): (Decimal("10"), po.po_number),
    }
    assert shares(b) == {str(p2.id): (Decimal("40"), po.po_number)}


def test_k8_an_spo_line_closed_with_nothing_landed_shows_on_the_po_line_as_withdrawn(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100, line_status="closed")
    detail = _svc(db).get_po_detail(str(po.id))
    [line] = detail["lines"]
    assert [(e["spo_number"], e["dead_reason"]) for e in line.get("spos", [])] == [
        (a.spo_number, "spo_withdrawn")
    ]
