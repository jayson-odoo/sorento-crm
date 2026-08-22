"""Captain ruling, 20 Aug (live test): "for reorder plan need to deduct both SPO and PO
to determine the suggested quantity."

Before this: `scm.net_position_v` (and therefore `_compute_cell`'s ``net``) only ever
netted on-hand + on-order SPO against committed demand. Outstanding PO sat on the frozen
row (S10, `scm.po_ordered_v`) DISPLAY-ONLY, so a row could read "Net -1,141" while its own
PO column read 3,642 outstanding for the exact same shortage - the plan recommended buying
stock a PO was already inbound for.

Traces to `app/services/scm/reorder_run_service.py::_compute_cell` (the ``net`` leg) and
``_covered_rec`` (the ``available`` leg the "use stock instead" suggestion is sized
against) - the two places a location's own buy/covered decision reads availability. Every
scope that sizes a buy (per-warehouse, pool, network) routes through `_compute_cell`'s
frozen `retail_net`, so one fix at the source covers all three (see
`test_channel_read_model.py`'s pool/network coverage for the routing itself; this file
pins only the new PO leg).

No double count (investigated, not assumed): `committed` only ever excludes a LINE CS
marked `purchasing_status='covered'` - a person ruling "no purchase needed", never "a PO
exists for it" (`models/order.py::SalesOrderLine.purchasing_status`). A line with a PO
raised against it keeps `purchasing_status='ordered'` and stays fully committed, so its PO
quantity was real, uncounted supply until this change - both tests below use the DEFAULT
`purchasing_status` (`not_reviewed`), matching the ordinary case.

Postgres only, marker-prefixed, every test seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import _link, _mk_product, _mk_stock, _mk_supplier, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTPONET"


def _u() -> str:
    return str(uuid.uuid4())


def _committed_line(db, pid, wid, qty) -> None:
    """One LOCATED, open `retail` SO line - the ordinary committed-demand case
    `scm.committed_v` counts regardless of any PO raised against it."""
    so = SalesOrder(id=_u(), so_number=f"{MARKER}-SO-{_u()[:8]}", status="open",
                    demand_class="retail")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=pid, warehouse_id=wid,
        qty_ordered=qty, qty_delivered=0, line_status="open",
    )
    db.add(line)
    db.flush()


def _mk_po_line(db, pid, wid, *, qty_ordered, qty_received=0) -> None:
    """One open `purchase_order_lines` row - the outstanding-PO leg `scm.po_ordered_v`
    reads. Mirrors `tests/scm/test_m0_view_correctness.py::test_on_order_v_excludes_draft_po`'s
    insert shape."""
    po_id = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, source_system) "
        "VALUES (:id, :num, 'active', 'test')"
    ), {"id": po_id, "num": f"{MARKER}-PO-{po_id[:8]}"})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_received, line_status, source_system) "
        "VALUES (:id, :po, :pid, :wid, :qo, :qr, 'open', 'test')"
    ), {"id": _u(), "po": po_id, "pid": pid, "wid": wid,
        "qo": qty_ordered, "qr": qty_received})


def _rec(db, run_id, pid, wid) -> dict:
    row = db.execute(text(
        "SELECT rec_type, rounded_qty, net_position, inputs FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND warehouse_id = :w"
    ), {"r": run_id, "p": pid, "w": wid}).mappings().first()
    assert row, "the SKU x warehouse must produce exactly one recommendation"
    return dict(row)


def test_a_po_that_fully_covers_committed_demand_turns_a_buy_into_covered(scm_app):
    """The captain's own example, in miniature: 0 on hand, 0 SPO, 3,642 committed, and a
    3,642 outstanding PO already raised against it. Before this fix the plan would net only
    on-hand + SPO (-3,642) and recommend buying it again; after, the PO leg brings net to 0
    and the row can only ever SUGGEST using the incoming PO (a `covered` row), never repeat
    the purchase."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, f"{MARKER}-A")
    pid = _mk_product(db, f"{MARKER}-A")
    _mk_stock(db, pid, wid, 0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier A"), moq=None, mult=None)
    _committed_line(db, pid, wid, 3642)
    _mk_po_line(db, pid, wid, qty_ordered=3642)
    db.flush()

    created = svc.create_run(db, [f"{MARKER}-A"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rec = _rec(db, created["run_id"], pid, wid)
    assert rec["rec_type"] == "covered", (
        "a fully-covering outstanding PO must turn this into a suggestion, not a repeat buy"
    )
    assert rec["net_position"] == pytest.approx(0.0), (
        "the frozen Net figure must net the PO leg too - this is the exact "
        "'Net -1,141 vs PO 3,642' mismatch the ruling names"
    )
    assert rec["inputs"]["po_ordered"] == pytest.approx(3642.0)
    assert rec["inputs"]["covered_committed"] == pytest.approx(3642.0)
    assert rec["inputs"]["covered_available"] == pytest.approx(3642.0), (
        "covered_available (on_hand + on_order + po_ordered) must carry the PO leg too, "
        "or the 'use stock' suggestion undercounts what is already on order"
    )
    assert rec["rounded_qty"] == pytest.approx(3642.0), (
        "the covered row still states the full committed quantity as what WOULD be "
        "bought - the planner's choice, not the engine's"
    )


def test_a_partial_po_reduces_the_suggested_buy_by_exactly_its_own_quantity(scm_app):
    """The PO does not have to fully cover the shortage to matter: 50 on hand, 500
    committed, and a 100-unit outstanding PO must reduce the suggested buy from 450 to
    350 - the PO quantity, netted once, exactly like SPO already was."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, f"{MARKER}-B")
    pid = _mk_product(db, f"{MARKER}-B")
    _mk_stock(db, pid, wid, 50)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier B"), moq=None, mult=None)
    _committed_line(db, pid, wid, 500)
    _mk_po_line(db, pid, wid, qty_ordered=100)
    db.flush()

    created = svc.create_run(db, [f"{MARKER}-B"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rec = _rec(db, created["run_id"], pid, wid)
    assert rec["rec_type"] == "buy"
    # net_position = on_hand(50) + on_order(0) + po_ordered(100) - committed(500) = -350
    assert rec["net_position"] == pytest.approx(-350.0)
    assert rec["inputs"]["po_ordered"] == pytest.approx(100.0)
    # order_up_to is 0 (no demand_stat -> demand_rate 0 -> rop/oup 0), so the sized buy is
    # 0 - (-350) = 350 - exactly 100 less than the pre-fix figure of 450 (50 on hand alone
    # against 500 committed), which is the PO quantity this change now nets.
    assert rec["rounded_qty"] == pytest.approx(350.0)
