"""LINKAGE-UNIFY U2 (PLAN section 8, item 4): Stock Debt reads the chain's received hops.

A placement on a PO line the book calls received but no shipping order names (class d) is
on hand where the Goods Received says it landed; a received SPO's goods are on hand at the
GR's bin, not the SPO's. A dead document holds nothing.

GR seeding is `tests/scm/test_goods_chain_received.py`'s (AutoCount shape: header
`picking_type 'goods_received'`, `picking_status 'approved'`, `doc_key` set; line `qty`,
`location_code`, `po_line_id` / `spo_allocation_id`). Same route and helpers as
`test_stock_debt_po_transferred.py`: SO1 (50) holds the placement, SO2 (50) has none.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import requires_pg
from tests.scm.test_goods_chain_received import (
    D1,
    D2,
    TODAY,
    gr_autocount,
)
from tests.scm.test_stock_debt_po_transferred import (
    _case,
    _po_rows,
    _transferred_onto,
)
from tests.scm.test_stock_debt_routes import (
    _assert_pinned_on_the_bin,
    _client,
    _product,
    _stock,
    _warehouse,
    _u,
    BASE,
)

pytestmark = requires_pg


class _P:
    """A `_World`-shaped stand-in for `gr_autocount` (it only reads `.product`)."""

    def __init__(self, product):
        self.product = product


def _so1(c, marker, product, due):
    cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
    return {line["so_number"]: line for line in cell["demand"]}[f"{marker}-SO1"]


def _from(line):
    return sorted((e["kind"], e["ref"], e["qty"]) for e in line["assigned_from"])


def test_seed_stock_debt_gr_chain_builds(scm_app):
    """Seeding only (passes today): the class d chain and its GR rows exist."""
    from app.models.procurement import PickingLine

    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    gr = gr_autocount(db, _P(product), qty=50, bin_code=warehouse.warehouse_code,
                      picking_date=D1, po_line=po_line)
    assert db.get(PickingLine, gr.id).po_line_id == po_line.id
    assert po_line.qty_received == po_line.qty_ordered


def test_ac_r3_class_d_placement_pins_the_on_hand_at_each_gr_bin(scm_app):
    """PO line 50 closed, 50 transferred, no SPO names it; GR 30 at B1, 70 at B2, both bins
    hold their stock. SO1's 50 pins 30 on B1's on hand and 20 on B2's."""
    app, db = _client(scm_app)
    marker, b1, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    b2 = _warehouse(db, f"ZZTBRW{_u()[:4]}-B2")
    gr_autocount(db, _P(product), qty=30, bin_code=b1.warehouse_code, picking_date=D1,
                 po_line=po_line)
    gr_autocount(db, _P(product), qty=70, bin_code=b2.warehouse_code, picking_date=D2,
                 po_line=po_line)
    _stock(db, product, b1, 30)
    _stock(db, product, b2, 70)
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
        cells = [
            c.get(f"{BASE}/{product.id}/cell", params={"month": m}).json()
            for m in (month_key(TODAY), month_key(due))
        ]
    assert so1["status"] == "pinned"
    assert so1["assigned_qty"] == 50
    assert _from(so1) == sorted([
        ("on_hand", f"On hand {b1.warehouse_code}", 30),
        ("on_hand", f"On hand {b2.warehouse_code}", 20),
    ])
    assert _po_rows(*cells) == []


def test_ac_r3_each_gr_pin_is_capped_by_what_the_bin_holds(scm_app):
    """The same GR split, but B2 has since shipped most of its goods (holds 5): the B2 pin
    is capped at 5, so SO1 holds 30 + 5 and reads short 15."""
    app, db = _client(scm_app)
    marker, b1, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    b2 = _warehouse(db, f"ZZTBRW{_u()[:4]}-B2")
    gr_autocount(db, _P(product), qty=30, bin_code=b1.warehouse_code, picking_date=D1,
                 po_line=po_line)
    gr_autocount(db, _P(product), qty=70, bin_code=b2.warehouse_code, picking_date=D2,
                 po_line=po_line)
    _stock(db, product, b1, 30)
    _stock(db, product, b2, 5)
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
    assert _from(so1) == sorted([
        ("on_hand", f"On hand {b1.warehouse_code}", 30),
        ("on_hand", f"On hand {b2.warehouse_code}", 5),
    ])
    assert so1["short_qty"] == 15


def test_ac_r4_class_d_placement_with_no_gr_pins_the_po_lines_own_bin(scm_app):
    """No GR line anywhere: the goods are on hand at the PO line's own bin, pinned there
    like a landed SPO (the AC-1/AC-2 shape)."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    _stock(db, product, warehouse, 50)
    with TestClient(app) as c:
        _assert_pinned_on_the_bin(c, marker=marker, warehouse=warehouse, product=product,
                                  due=due)


def test_ac_r6_a_dead_po_line_holds_nothing(scm_app):
    """PO line cancelled with nothing transferred: nothing on order, nothing received, so
    SO1 reads short with no assigned-from and no PO row."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(
        db, ordered=50, transferred=0, open_line=False,
    )
    po_line.line_status = "cancelled"
    db.flush()
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
        cells = [
            c.get(f"{BASE}/{product.id}/cell", params={"month": m}).json()
            for m in (month_key(TODAY), month_key(due))
        ]
    assert so1["status"] == "short"
    assert so1["assigned_from"] == []
    assert _po_rows(*cells) == []


def test_ac_r6_a_cancel_po_line_holds_nothing_even_with_stock_at_its_bin(scm_app):
    """A Cancel PO line (`qty_cancelled = qty_received`) is dead: it must not pin the
    bin's on hand as if the goods had been received there."""
    from decimal import Decimal

    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    po_line.qty_cancelled = Decimal("50")
    db.flush()
    _stock(db, product, warehouse, 50)
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
    assert so1["status"] != "pinned"
    assert [e for e in so1["assigned_from"] if e["kind"] == "po"] == []


def test_ac_r7_a_received_spo_pins_the_gr_bin_not_the_spo_bin(scm_app):
    """SPO A landed 50 with SPO bin B1, but the GR naming it received at B2 (OI-2609-0352
    L1216: SPO BRW-BB, GR at MWH). Only B2 holds the goods: SO1 pins B2's on hand, where
    today it reads B1's empty bin and comes out short."""
    app, db = _client(scm_app)
    marker, b1, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    b2 = _warehouse(db, f"ZZTBRW{_u()[:4]}-B2")
    a = _transferred_onto(
        db, product, po, po_line, b1, qty=50, received=50, receipt_status="fully_received",
        arrives=TODAY - timedelta(days=10),
    )
    a.line_status = "closed"
    db.flush()
    gr_autocount(db, _P(product), qty=50, bin_code=b2.warehouse_code, picking_date=D1, spo=a)
    _stock(db, product, b2, 50)
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
    assert so1["status"] == "pinned"
    assert _from(so1) == [("on_hand", f"On hand {b2.warehouse_code}", 50)]


def test_r_a_partial_cancel_po_on_an_open_line_still_pins_the_po(scm_app):
    """PO line 100, Cancel PO took 40 (received 40, cancelled 40), line open, no SPO: the
    60 on order is live supply, SO1's placement of 50 pins the PO for 50 (as before U2)."""
    from decimal import Decimal

    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=100, transferred=40)
    po_line.qty_cancelled = Decimal("40")
    db.flush()
    with TestClient(app) as c:
        so1 = _so1(c, marker, product, due)
    assert so1["status"] == "pinned"
    assert [(e["kind"], e["qty"]) for e in so1["assigned_from"]] == [("po", 50)]
