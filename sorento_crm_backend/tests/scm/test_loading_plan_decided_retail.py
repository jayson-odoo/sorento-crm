"""DEALER-PLANNING PR 2, R15: a confirmed retail line stays on the Loading Plan.

Today a retail line an active supply decision covers drops out of the Retail column
(`is_plan_demand_line`), because the decision "handles" it. Once retail orders are planned
the decision is only a statement of where the stock comes from: a Buy still has to be asked of
the supplier, and a Reserve is still demand the Loading Plan must see to net against stock.
So a decided retail line stays, ONCE, in the Retail column, less its SPO links (as a project
line is), and its product keeps its demand row.

Figures (UAC R15): Buy 10 with 0 on hand: Retail 10, ask 10. Reserve 10 with 10 on hand:
Retail 10, ask 0. 4 of it linked to an SPO: Retail 6. `so_count` counts an order once.
Undecided retail and every project figure are unchanged, and `build`'s invariant (the
`sum(qty)` of a product's lines equals its `open_so_need`) holds.

Seeded from the helpers of `test_container_request_universe.py` (chain, SPO link) and
`test_container_request.py` (stock). A decision is written the way the planning board
writes one: an active `SOSupplyDecision` whose `line_snapshots` name the core line.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.inventory import Stock
from app.models.order import SalesOrderLine
from app.models.project_so import SOSupplyDecision
from app.services.scm import container_request_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_container_request import _on_hand, _warehouse
from tests.scm.test_container_request_universe import (
    _build,
    _linked,
    _place_chain,
    _place_spo,
    _project_need,
    _retail_need,
    _row,
)
from tests.scm.test_loading_plan import World


def _line_of(db, so):
    return db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == so.id).one()


def _decide(db, w, line):
    """CS confirmed this line: an active decision covering it (a Buy or a Reserve alike)."""
    _place_chain(db, w, line)
    from app.models.project_so import ProjectSalesOrder

    pso = db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == line.sales_order_id).one()
    db.add(
        SOSupplyDecision(
            id=str(uuid.uuid4()),
            company_id=pso.company_id,
            project_sales_order_id=pso.id,
            revision_no=1,
            state="active",
            line_snapshots=[{"core_line_id": str(line.id)}],
        )
    )
    db.flush()


def _decided_retail(db, w, key, qty):
    so = _retail_need(db, w, key, qty, required=date(2026, 6, 1))
    line = _line_of(db, so)
    _decide(db, w, line)
    return so, line


def test_r15_a_confirmed_buy_with_nothing_on_hand_stays_in_retail_and_is_asked_for():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _decided_retail(db, w, "A", 10)

        row = _row(_build(db, w), w, "A")

    assert row["retail_qty"] == 10
    assert row["open_so_need"] == 10
    assert row["has_demand"] is True
    assert row["suggested_qty"] == 10


def test_r15_a_confirmed_reserve_with_the_stock_on_hand_stays_in_retail_and_asks_for_nothing():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _decided_retail(db, w, "A", 10)
        _on_hand(db, w, "A", _warehouse(db), 10)

        row = _row(_build(db, w), w, "A")

    assert row["retail_qty"] == 10
    assert row["on_hand"] == 10
    assert row["suggested_qty"] == 0


def test_r15_what_is_linked_to_an_spo_comes_off_the_retail_figure():
    """4 of the 10 are on a shipping order, so Retail is 6."""
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _so, line = _decided_retail(db, w, "A", 10)
        _place_spo(db, w, line, 4)

        row = _row(_build(db, w), w, "A")

    assert row["retail_qty"] == 6
    assert row["open_so_need"] == 6


def test_r15_the_line_is_listed_once_and_the_lines_foot_to_the_demand_row():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _so, line = _decided_retail(db, w, "A", 10)
        _place_spo(db, w, line, 4)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)
        row = _row(out, w, "A")
        mine = [l for l in out["lines"] if l["product_id"] == str(w.product("A").id)]

    assert len(mine) == 1
    assert mine[0]["demand_class"] == "retail"
    assert sum(l["qty"] for l in mine) == row["open_so_need"] == 6


def test_r15_an_order_with_a_decided_and_an_undecided_line_counts_once():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        so, _line = _decided_retail(db, w, "A", 10)
        db.add(
            SalesOrderLine(
                id=str(uuid.uuid4()),
                sales_order_id=so.id,
                product_id=w.product("A").id,
                qty_ordered=5,
                qty_delivered=0,
                line_status="open",
                purchasing_status="not_reviewed",
                required_date=date(2026, 6, 1),
            )
        )
        db.flush()

        row = _row(_build(db, w), w, "A")

    assert row["retail_qty"] == 15
    assert row["so_count"] == 1


def test_r15_undecided_retail_and_every_project_figure_are_unchanged():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 20)
        _project_need(db, w, "A", 30)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)
        row = _row(out, w, "A")
        lines = [l for l in out["lines"] if l["product_id"] == str(w.product("A").id)]

    assert (row["retail_qty"], row["project_qty"], row["open_so_need"]) == (20, 30, 50)
    assert row["so_count"] == 2
    assert sum(l["qty"] for l in lines) == row["open_so_need"]


def test_r15_a_decided_retail_line_beside_project_demand_keeps_both_figures():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _decided_retail(db, w, "A", 10)
        _project_need(db, w, "A", 30)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)
        row = _row(out, w, "A")
        lines = [l for l in out["lines"] if l["product_id"] == str(w.product("A").id)]

    assert (row["retail_qty"], row["project_qty"], row["open_so_need"]) == (10, 30, 40)
    assert row["so_count"] == 2
    assert sum(l["qty"] for l in lines) == row["open_so_need"]
