"""LINKAGE-UNIFY U1 (PLAN-linkage-unify-26oct section 7): the goods chain.

`app.services.scm.goods_chain` answers, per live placement (`order_inquiry_links` row),
where the placed goods are: on the PO (`po` hop, `on_order`), on an SPO the PO line was
transferred onto (`spo` hop, `in_transit` or `received`). AC-C1..AC-C7 are the contract;
AC-C8 (Stock Debt unchanged) is the existing suites, not this file.

Every test seeds its own chain (company rows, product, bins, SO + project line, OI row,
PO line with `source_ref`, SPO allocation naming it): CI's database is empty. The module is
imported lazily so that, before it exists, each test fails on its own import error.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_po_transferred import _po_line, _transferred_onto
from tests.scm.test_stock_debt_routes import (
    _demand,
    _months_ahead,
    _order_back_link_on_po,
    _order_back_link_on_spo,
    _product,
    _project_line_for,
    _spo,
    _u,
    _warehouse,
)

pytestmark = requires_pg

TODAY = date.today()
T0 = datetime(2026, 1, 1, 9, 0, 0)


def _gc():
    return importlib.import_module("app.services.scm.goods_chain")


class _World:
    """One product, bins B1 and B2, and a counter so each placement gets its own SO line."""

    def __init__(self, db):
        self.db = db
        self.marker = f"ZZTGC{_u()[:6]}".upper()
        self.b1 = _warehouse(db, f"ZZTB1{_u()[:4]}")
        self.b2 = _warehouse(db, f"ZZTB2{_u()[:4]}")
        self.product = _product(db, f"{self.marker}-A")
        self.due = _months_ahead(1)
        self._n = 0

    def _project_line(self, qty):
        self._n += 1
        _order, core = _demand(
            self.db, self.product, self.b1, qty=qty, required_date=self.due,
            so_number=f"{self.marker}-SO{self._n}",
        )
        return _project_line_for(self.db, core)

    def po(self, *, ordered, transferred, open_line=None):
        return _po_line(
            self.db, self.product, self.b1, ordered=ordered, transferred=transferred,
            open_line=open_line,
        )

    def onto(self, po, po_line, *, qty, received=0, status="pending", arrives=None,
             line_status="open", warehouse=None):
        allocation = _transferred_onto(
            self.db, self.product, po, po_line, warehouse or self.b1, qty=qty,
            received=received, receipt_status=status, arrives=arrives or self.due,
        )
        allocation.line_status = line_status
        self.db.flush()
        return allocation

    def place_on_po(self, po_line, qty, minute=0):
        order, line = self._project_line(qty)
        row, link = _order_back_link_on_po(self.db, order, line, po_line=po_line, qty=qty)
        link.linked_at = T0 + timedelta(minutes=minute)
        self.db.flush()
        return row, link

    def place_on_spo(self, allocation, qty, minute=0):
        order, line = self._project_line(qty)
        _inq, row, link = _order_back_link_on_spo(
            self.db, order, line, allocation=allocation, qty=qty,
        )
        link.linked_at = T0 + timedelta(minutes=minute)
        self.db.flush()
        return row, link


def _hops(chain):
    """Compact view: (kind, state, qty, document number, bin code)."""
    return [
        (
            hop.kind,
            hop.state,
            Decimal(str(hop.qty)),
            hop.spo_number if hop.kind == "spo" else hop.po_number,
            hop.warehouse_code if hop.kind == "spo" else None,  # po-hop bin left open in U1
        )
        for hop in chain.hops
    ]


def _chain(db, link):
    out = _gc().chains_for_links(db, [str(link.id)])
    assert str(link.id) in out
    return out[str(link.id)]


# ---------------------------------------------------------------------------- seed check


def test_seed_chain_builds(scm_app):
    """Seeding only (passes today): the AC-C3 chain exists row by row."""
    from app.models.procurement import PurchaseOrderLine, SPOAllocation
    from app.models.project_so import OrderInquiryLink, OrderInquiryRow

    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    spo = w.onto(po, po_line, qty=100, received=100, status="fully_received",
                 line_status="closed", arrives=TODAY - timedelta(days=5))
    row, link = w.place_on_po(po_line, 50)
    assert db.get(PurchaseOrderLine, po_line.id).source_ref
    assert db.get(SPOAllocation, spo.id).from_po_line_ref == po_line.source_ref
    assert db.get(SPOAllocation, spo.id).from_po_number == po.po_number
    assert db.get(OrderInquiryRow, row.id).state != "cancelled"
    assert db.get(OrderInquiryLink, link.id).po_line_id == po_line.id
    assert db.get(OrderInquiryLink, link.id).linked_at == T0


# ---------------------------------------------------------------------------- AC-C1..C5


def test_ac_c1_on_order(scm_app):
    """PO line 100 ordered, 0 transferred, open; placement 50: one `po` hop on_order 50."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=0)
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert [h.kind for h in chain.hops] == ["po"]
    assert _hops(chain) == [("po", "on_order", Decimal("50"), po.po_number, None)]
    assert chain.hops[0].po_line_id == str(po_line.id)
    assert chain.hops[0].purchase_order_id == str(po.id)
    assert chain.unplaced_qty == Decimal("0")


def test_ac_c2_in_transit(scm_app):
    """PO line 100 transferred onto SPO A 100, 0 received, open: one `spo` hop in_transit
    50 and no `po` hop."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100)
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _hops(chain) == [("spo", "in_transit", Decimal("50"), a.spo_number, None)]
    assert chain.hops[0].spo_allocation_id == str(a.id)
    assert chain.unplaced_qty == Decimal("0")


def test_ac_c3_received(scm_app):
    """As C2 but SPO A 100/100 fully_received, closed, bin B1: `spo` hop received 50 at B1."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100, received=100, status="fully_received",
               line_status="closed", arrives=TODAY - timedelta(days=5))
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _hops(chain) == [
        ("spo", "received", Decimal("50"), a.spo_number, w.b1.warehouse_code)
    ]
    assert chain.hops[0].warehouse_id == str(w.b1.id)
    assert chain.unplaced_qty == Decimal("0")


def test_ac_c4_partial_transfer(scm_app):
    """PO line 100, 40 transferred onto SPO A 40 in transit; placement 100: `spo` A
    in_transit 40, then `po` on_order 60."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=40)
    a = w.onto(po, po_line, qty=40)
    _row, link = w.place_on_po(po_line, 100)
    chain = _chain(db, link)
    assert _hops(chain) == [
        ("spo", "in_transit", Decimal("40"), a.spo_number, None),
        ("po", "on_order", Decimal("60"), po.po_number, None),
    ]
    assert chain.unplaced_qty == Decimal("0")


def test_ac_c5_shared_capacity_is_screen_independent(scm_app):
    """PO line 120 onto SPO A 70 (earlier) and SPO B 50 (later), both in transit. P1 60
    (first), P2 60: P1 = A 60; P2 = A 10 + B 50. P2 asked alone answers the same."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=120, transferred=120)
    a = w.onto(po, po_line, qty=70, arrives=w.due.replace(day=1))
    b = w.onto(po, po_line, qty=50, arrives=w.due.replace(day=9))
    _r1, p1 = w.place_on_po(po_line, 60, minute=1)
    _r2, p2 = w.place_on_po(po_line, 60, minute=2)

    both = _gc().chains_for_links(db, [str(p1.id), str(p2.id)])
    assert _hops(both[str(p1.id)]) == [("spo", "in_transit", Decimal("60"), a.spo_number, None)]
    expected_p2 = [
        ("spo", "in_transit", Decimal("10"), a.spo_number, None),
        ("spo", "in_transit", Decimal("50"), b.spo_number, None),
    ]
    assert _hops(both[str(p2.id)]) == expected_p2
    alone = _gc().chains_for_links(db, [str(p2.id)])
    assert _hops(alone[str(p2.id)]) == expected_p2
    assert both[str(p2.id)].unplaced_qty == Decimal("0")


# ---------------------------------------------------------------------------- AC-C6


def _closed_po_with_decoy(db, *, mutate):
    """PO 100/100 closed, placement 50, and one SPO naming it that `mutate` spoils."""
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100)
    mutate(w, a, po, po_line)
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    return w, a, link


def _assert_not_followed(db, link):
    chain = _chain(db, link)
    assert chain.hops == ()
    assert chain.unplaced_qty == Decimal("50")


def test_ac_c6_other_po_number_not_followed(scm_app):
    db = scm_app[1]

    def spoil(w, a, po, po_line):
        a.from_po_number = f"{po.po_number}X"

    _w, _a, link = _closed_po_with_decoy(db, mutate=spoil)
    _assert_not_followed(db, link)


def test_ac_c6_other_product_not_followed(scm_app):
    db = scm_app[1]

    def spoil(w, a, po, po_line):
        a.product_id = _product(db, f"{w.marker}-OTHER").id

    _w, _a, link = _closed_po_with_decoy(db, mutate=spoil)
    _assert_not_followed(db, link)


def test_ac_c6_other_company_not_followed(scm_app):
    from app.models.base import set_company_scope
    from app.models.company import Company

    db = scm_app[1]
    other = _u()
    db.add(Company(id=other, name="ZZT GC other", code=f"ZZTGC{_u()[:6]}".upper(),
                   is_active=True))
    db.flush()

    def spoil(w, a, po, po_line):
        a.company_id = other

    _w, _a, link = _closed_po_with_decoy(db, mutate=spoil)
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    _assert_not_followed(db, link)


def test_ac_c6_space_padded_ref_is_followed(scm_app):
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=100)
    a.from_po_line_ref = f"  {po_line.source_ref} "
    db.flush()
    _row, link = w.place_on_po(po_line, 50)
    chain = _chain(db, link)
    assert _hops(chain) == [("spo", "in_transit", Decimal("50"), a.spo_number, None)]


def test_ac_c6_retired_spo_with_nothing_received_not_followed(scm_app):
    db = scm_app[1]

    def spoil(w, a, po, po_line):
        a.retired_at = datetime.utcnow()

    _w, _a, link = _closed_po_with_decoy(db, mutate=spoil)
    _assert_not_followed(db, link)


# ---------------------------------------------------------------------------- AC-C7


def test_ac_c7_nothing_left_for_the_second_placement(scm_app):
    """PO line 100 closed, 100 transferred, only SPO A 50 (in transit) names it. P1 50
    (first): `spo` A in_transit 50. P2 50: no hop, unplaced 50."""
    db = scm_app[1]
    w = _World(db)
    po, po_line = w.po(ordered=100, transferred=100)
    a = w.onto(po, po_line, qty=50)
    _r1, p1 = w.place_on_po(po_line, 50, minute=1)
    _r2, p2 = w.place_on_po(po_line, 50, minute=2)
    out = _gc().chains_for_links(db, [str(p1.id), str(p2.id)])
    assert _hops(out[str(p1.id)]) == [("spo", "in_transit", Decimal("50"), a.spo_number, None)]
    assert out[str(p1.id)].unplaced_qty == Decimal("0")
    assert out[str(p2.id)].hops == ()
    assert out[str(p2.id)].unplaced_qty == Decimal("50")


# ---------------------------------------------------------------------------- direct SPO


def test_direct_spo_placement_in_transit(scm_app):
    """A placement straight on an incoming SPO: `spo` hop in_transit for the placement
    qty (not capped: `assign()` caps)."""
    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    _row, link = w.place_on_spo(a, 30)
    chain = _chain(db, link)
    assert _hops(chain) == [("spo", "in_transit", Decimal("30"), a.spo_number, None)]
    assert chain.unplaced_qty == Decimal("0")


def test_direct_spo_placement_received_is_capped_at_landed(scm_app):
    """Not incoming: `received` for min(qty, landed) at the SPO's bin. Landed 100, qty 30
    -> 30; landed 20, qty 30 -> 20 with 10 unplaced."""
    db = scm_app[1]
    w = _World(db)
    big = _spo(db, w.product, w.b2, qty=100, arrives=TODAY - timedelta(days=3), received=100,
               receipt_status="fully_received", line_status="closed")
    small = _spo(db, w.product, w.b2, qty=20, arrives=TODAY - timedelta(days=3), received=20,
                 receipt_status="fully_received", line_status="closed")
    _r1, l1 = w.place_on_spo(big, 30)
    _r2, l2 = w.place_on_spo(small, 30)
    code = w.b2.warehouse_code
    c1 = _chain(db, l1)
    assert _hops(c1) == [("spo", "received", Decimal("30"), big.spo_number, code)]
    assert c1.hops[0].warehouse_id == str(w.b2.id)
    c2 = _chain(db, l2)
    assert _hops(c2) == [("spo", "received", Decimal("20"), small.spo_number, code)]
    assert c2.unplaced_qty == Decimal("10")


# ---------------------------------------------------------------------------- scoping, order


def test_a_link_on_a_cancelled_row_is_absent(scm_app):
    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    row, link = w.place_on_spo(a, 30)
    _row2, live = w.place_on_spo(a, 10, minute=5)
    row.state = "cancelled"
    db.flush()
    out = _gc().chains_for_links(db, [str(link.id), str(live.id)])
    assert str(link.id) not in out
    assert str(live.id) in out
    assert str(row.id) not in _gc().chains_for_rows(db, [str(row.id)])


def test_chains_for_rows_come_back_in_linked_at_order(scm_app):
    """Two links on one row: the row answers them by `linked_at`, not by insertion."""
    from app.models.project_so import OrderInquiryLink

    db = scm_app[1]
    w = _World(db)
    a = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    b = _spo(db, w.product, w.b1, qty=100, arrives=w.due)
    row, first_made = w.place_on_spo(a, 10, minute=30)
    second_made = OrderInquiryLink(
        id=_u(), company_id=SORENTO_COMPANY_ID, row_id=row.id, spo_allocation_id=b.id,
        qty=Decimal("20"), linked_at=T0 + timedelta(minutes=10),
    )
    db.add(second_made)
    db.flush()
    chains = _gc().chains_for_rows(db, [str(row.id)])[str(row.id)]
    assert [c.link_id for c in chains] == [str(second_made.id), str(first_made.id)]
    assert all(c.row_id == str(row.id) for c in chains)
    assert [c.placed_qty for c in chains] == [Decimal("20"), Decimal("10")]
