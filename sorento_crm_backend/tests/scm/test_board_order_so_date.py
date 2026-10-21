"""OI-SPLIT-CONFIRM-POLISH (owner, SO426939, 21 Oct 2026): the board's `orders[]` carries the
order's SO date, so the guided Confirm's Review split prints SO DATE on an order that has no
split read yet (nobody adopted it, so there is no planning record to read).

`so_date` is the core sales order's own document date, the same value the split read's
`_core_order_date` returns for an adopted order.

Helpers and the `api` fixture come from `tests/test_planning_changes.py` (same world, same
Postgres chain).
"""
from __future__ import annotations

from datetime import date

from tests.scm.test_planning_change_gate_held_or_inquiry import _adopted_line
from tests.test_planning_changes import BASE, _core_line, _core_so, api  # noqa: F401

SO_DATE = date(2026, 10, 20)


def test_board_orders_carry_the_core_so_date_adopted_or_not(api):
    client, world = api
    db = world.db

    adopted_so = _core_so(db, world.company_id)
    adopted_so.order_date = SO_DATE
    _adopted_line(db, world, qty="5", core_so=adopted_so)

    unadopted_so = _core_so(db, world.company_id)
    unadopted_so.order_date = SO_DATE
    _core_line(db, unadopted_so, world.product, world.own_wh, qty_ordered="3")

    undated_so = _core_so(db, world.company_id)
    _core_line(db, undated_so, world.product, world.own_wh, qty_ordered="2")
    db.commit()

    names = [adopted_so.so_number, unadopted_so.so_number, undated_so.so_number]
    response = client.get(f"{BASE}/fulfilment-planning/board", params={"orders": ",".join(names)})
    assert response.status_code == 200, response.text
    by_so = {order["so_number"]: order for order in response.json()["orders"]}

    assert by_so[adopted_so.so_number]["so_date"] == "2026-10-20"
    assert by_so[unadopted_so.so_number]["project_sales_order_id"] is None
    assert by_so[unadopted_so.so_number]["so_date"] == "2026-10-20"
    assert by_so[undated_so.so_number]["so_date"] is None
