"""A reconfirm RECONCILES the open transfers, it does not sweep them (ruling R16, 27 Aug 2026).

The evidence run on the board's single Confirm: amending ONE line of a 37-line order
re-proposed 25 movements and every approval a planner had already given went back to
`proposed` under a new document number. The old rule cancelled every open transfer of the
order on each confirm and wrote the whole composition fresh, which was safe while Confirm was
pressed per order and per line, and is a daily loss of work now that one press reconfirms the
whole board.

So the writer compares what the new revision implies with what is already open, keyed on
`(so_line_id, product_id, from_warehouse_id, to_warehouse_id, kind)` - the five facts that
make two rows the same instruction to a warehouse:

* the SAME movement at the SAME quantity is KEPT, state and approval intact, and re-pointed at
  the new revision;
* a movement that GREW keeps its row and gets a second one for the difference;
* a movement that SHRANK is cancelled and re-proposed at the new quantity;
* a movement that VANISHED is cancelled;
* a movement nobody had is proposed.

`moved` rows are untouched throughout and still net out of what is proposed, exactly as
before: stock that has physically moved is history.

Postgres via `tests/_pg_fixture.py`, never sqlite. The world and its seed helpers are
`test_stock_transfers.py`'s, so the two files cannot disagree about the shape of a transfer.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.stock_transfer import StockTransfer

from .test_stock_transfers import (  # noqa: F401 - `api` is a fixture, used by name
    BASE,
    api,
    qty_of,
    _one_line_order,
    _transfers,
)
from .test_so_supply_confirmation import _core_line, _core_so, _line_payload, _project_line
from .test_so_supply_confirmation import _project_so, _stock


def _confirm(client, order, lines):
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json={"lines": lines})
    assert response.status_code == 200, response.text
    return response.json()


def _two_line_order(world, *, qty_a="10", qty_b="20"):
    """One order, two lines, both at the line's own location - the board's own shape."""
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty_a)
    core_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty_b)
    line_a = _project_line(db, order, line_no=10, product=world.product, core_line=core_a)
    line_b = _project_line(db, order, line_no=20, product=world.product, core_line=core_b)
    db.commit()
    return order, line_a, line_b


def test_an_approved_transfer_survives_a_reconfirm_of_another_line(api):
    """R16, the case that cost the evidence run: line B is amended, line A's approved
    movement is the same instruction it was, so it keeps its number, its state and the
    person who approved it."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    _stock(db, world.product, world.sibling_wh, on_hand=900)
    order, line_a, line_b = _two_line_order(world)

    _confirm(
        client,
        order,
        [
            _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]),
            _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}]),
        ],
    )
    rows = _transfers(db, order.id)
    assert len(rows) == 2
    approved = next(row for row in rows if qty_of(row) == Decimal("10"))
    approve = client.post(f"/api/v1/inventory/stock-transfers/{approved.id}/approve")
    assert approve.status_code == 200, approve.text
    db.expire_all()
    approved = db.query(StockTransfer).filter(StockTransfer.id == approved.id).one()
    assert approved.state == "approved"
    approved_no, approved_at = approved.transfer_no, approved.approved_at

    # The second press: line A unchanged, line B recomposed - 15 from the pool and 5 from
    # the group sibling, which is still the whole 20 from stock (the confirmation refuses a
    # line that mixes stock with a Buy).
    result = _confirm(
        client,
        order,
        [
            _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]),
            _line_payload(
                line_b.id,
                reserve=[
                    {"warehouse_id": world.pool_wh.id, "qty": "15"},
                    {"warehouse_id": world.sibling_wh.id, "qty": "5"},
                ],
            ),
        ],
    )

    db.expire_all()
    kept = db.query(StockTransfer).filter(StockTransfer.id == approved.id).one()
    assert kept.state == "approved", "an approval a person gave is not thrown away"
    assert kept.transfer_no == approved_no
    assert kept.approved_at == approved_at
    # Re-pointed at the revision that now asks for it, so the page reads the live one.
    assert str(kept.supply_decision_id) is not None
    # Only line B's movements are rewritten: its pool row cancelled at 20 and re-proposed at
    # 15, with a second row for the 5 the sibling now sends.
    live = sorted(
        qty_of(row) for row in _transfers(db, order.id) if row.state == "proposed"
    )
    assert live == [Decimal("5"), Decimal("15")]
    cancelled = [row for row in _transfers(db, order.id) if row.state == "cancelled"]
    assert [qty_of(row) for row in cancelled] == [Decimal("20")]
    assert result["transfers_written"] == 2
    assert result["transfers_kept"] == 1


def test_a_movement_whose_quantity_shrank_is_cancelled_and_re_proposed(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so_row, core_line, line = _one_line_order(world, qty="71")

    _confirm(
        client,
        order,
        [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])],
    )
    # The book comes back with the line cut, which is what shrinks a movement in practice.
    core_line.qty_ordered = Decimal("40")
    line.qty = Decimal("40")
    db.flush()
    db.commit()

    result = _confirm(
        client,
        order,
        [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}])],
    )

    db.expire_all()
    rows = _transfers(db, order.id)
    assert sorted((row.state, qty_of(row)) for row in rows) == [
        ("cancelled", Decimal("71")),
        ("proposed", Decimal("40")),
    ]
    assert result["transfers_written"] == 1
    assert result["transfers_kept"] == 0


def test_a_movement_that_grew_keeps_its_row_and_gets_the_difference(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so_row, core_line, line = _one_line_order(world, qty="71")

    _confirm(
        client,
        order,
        [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])],
    )
    core_line.qty_ordered = Decimal("100")
    line.qty = Decimal("100")
    db.flush()
    db.commit()

    result = _confirm(
        client,
        order,
        [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "100"}])],
    )

    db.expire_all()
    rows = _transfers(db, order.id)
    assert sorted((row.state, qty_of(row)) for row in rows) == [
        ("proposed", Decimal("29")),
        ("proposed", Decimal("71")),
    ], "the 71 already asked for stands; only the difference is a new instruction"
    assert result["transfers_written"] == 1
    assert result["transfers_kept"] == 1


def test_a_movement_that_vanished_is_cancelled(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    order, _core_so_row, _core_line_row, line = _one_line_order(world, qty="71")

    _confirm(
        client,
        order,
        [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "71"}])],
    )
    result = _confirm(
        client,
        order,
        [_line_payload(line.id, buy_qty="71", buy_reason="bought instead")],
    )

    db.expire_all()
    rows = _transfers(db, order.id)
    assert [(row.state, qty_of(row)) for row in rows] == [("cancelled", Decimal("71"))]
    assert rows[0].cancelled_reason == "Superseded by revision 2"
    assert result["transfers_written"] == 0
    assert result["transfers_kept"] == 0


def test_a_movement_nobody_had_is_proposed(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=900)
    _stock(db, world.product, world.sibling_wh, on_hand=900)
    order, line_a, line_b = _two_line_order(world)

    _confirm(
        client,
        order,
        [_line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])],
    )
    result = _confirm(
        client,
        order,
        [
            _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]),
            _line_payload(
                line_b.id, reserve=[{"warehouse_id": world.sibling_wh.id, "qty": "20"}]
            ),
        ],
    )

    db.expire_all()
    live = sorted(
        qty_of(row) for row in _transfers(db, order.id) if row.state == "proposed"
    )
    assert live == [Decimal("10"), Decimal("20")]
    assert result["transfers_written"] == 1
    assert result["transfers_kept"] == 1
