"""RESERVE-DIALOG-ON-HAND (owner 11 Nov 2026: "reserve dialog actually we should just show
on hand qty simple as that").

The reserve dialogs (`RequestReserveDialog`, `ReserveLineForm`) read their per-pool figure
through `useReserveRowOptions`, which reads `locations[].qty_on_hand` off
`GET /fulfilment-planning/stock-detail?group=pools`. This pins that field as the plain
`stock.quantity_on_hand` at the pool: an open line on a NON-transferable sales order and an
open SPO allocation at the same pool move `available_qty`, never `qty_on_hand`.

Postgres, blank scratch schema, every FK target seeded (CI's database is empty).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ._pg_fixture import blank_session
from .test_fulfilment_board import (
    _incoming,
    _line,
    _order,
    _pool,
    _product,
    _service,
    _stock,
    _uid,
    _warehouse,
)


def test_pools_read_states_plain_on_hand_beside_non_transferable_so_and_open_spo():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        pool = _pool(db, f"ZZP{_uid()[:4]}")
        member = _warehouse(db, f"{pool.warehouse_code}-BB")
        member.pool_warehouse_id = pool.id
        db.flush()
        _stock(db, product, pool, on_hand=171)

        order = _order(db, so_number=f"ZZT-SO-{_uid()[:6]}")
        order.is_transferable = False
        db.flush()
        _line(db, order, product, qty="6", required_date=date(2026, 12, 1), warehouse=pool)
        _incoming(
            db, product, pool, spo_number=f"ZZT-SPO-{_uid()[:6]}",
            allocated=4, received=0, arrives=date(2026, 12, 15),
        )

        detail = _service(db).stock_detail(str(product.id), None, group="pools")

        entry = next(e for e in detail["locations"] if e["warehouse_id"] == str(pool.id))
        assert Decimal(entry["qty_on_hand"]) == Decimal("171"), entry
        # The fixture really does move the old figure, so the assertion above is not vacuous.
        assert Decimal(entry["available_qty"]) != Decimal("171"), entry
