"""Borrow candidate carries the board's own Location row (S4, PLAN-local-supplier-oi-routing.md,
UAC AC-2.20 - AC-2.21).

RED for AC-2.20: `borrow_candidates[]` has no `location` key yet, so the board test below
fails on a `KeyError`. Fixtures copied straight from `tests/test_fulfilment_board.py`
(`_product`, `_warehouse`, `_stock`, `_order`, `_line`, `_service`, `_cell`, `_uid`,
`TODAY`) - same scenario as that file's own
`test_a_board_borrow_candidate_carries_what_it_takes_to_confirm_it`, extended to compare
the candidate's new `location` against the cell's existing `locations` table entry for the
same donor warehouse.

AC-2.21 is `stock_detail`'s existing cross-group behaviour (the endpoint takes an
arbitrary `warehouse_id` with no group restriction already) - written here as the
regression proof the plan calls for; if it turns out already green against current code
that is reported to the captain rather than forced red, per the tester brief.
"""
from __future__ import annotations

from datetime import date

from tests.test_fulfilment_board import (  # noqa: F401  (fixtures/helpers, not tests)
    TODAY,
    _cell,
    _line,
    _order,
    _product,
    _service,
    _stock,
    _uid,
    _warehouse,
)
from tests._pg_fixture import blank_session

LOCATION_KEYS = (
    "qty_on_hand", "so_qty", "spo_qty", "available_qty", "available_for_project",
    "po_open_qty", "where", "warehouse_id",
)


def test_candidate_carries_location_in_cell_shape():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
        elsewhere = _warehouse(db, f"ZZTE{_uid()[:6]}"[:20])
        _stock(db, product, own, on_hand=0)
        _stock(db, product, elsewhere, on_hand=25)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-31")["contributions"][0]
        candidate = contribution["borrow_candidates"][0]

        assert "location" in candidate, "borrow_candidates[] must carry a location object"
        location = candidate["location"]
        for key in LOCATION_KEYS:
            assert key in location, key

        assert location["warehouse_id"] == str(elsewhere.id)

        # Same figures as the Grid Location table for the SAME warehouse, same request.
        grid_row = next(
            row for row in contribution["locations"] if row["warehouse_id"] == str(elsewhere.id)
        )
        for key in ("qty_on_hand", "so_qty", "spo_qty", "available_qty", "po_open_qty"):
            assert location[key] == grid_row[key], key


def test_stock_detail_cross_group_donor_marks_this_line():
    """`stock_detail(product_id, warehouse_id, line_ids=)` for a warehouse OUTSIDE the
    asking line's own ownership group still correctly flags that line's own row
    `is_this_line` - a plain membership check, with no group-scoping that could silently
    exclude a genuine cross-group donor read."""
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        donor = _warehouse(db, f"ZZTD{_uid()[:6]}"[:20])
        earlier_order = _order(db, so_number=f"ZZT-SO-EARLY-{_uid()[:6]}", order_date=date(2026, 3, 1))
        _line(db, earlier_order, product, qty="1", required_date=date(2026, 4, 1), warehouse=donor)
        asking_order = _order(db, so_number=f"ZZT-SO-ASK-{_uid()[:6]}", order_date=date(2026, 1, 1))
        asking_line = _line(
            db, asking_order, product, qty="24", required_date=date(2026, 6, 29), warehouse=donor,
        )

        detail = _service(db).stock_detail(
            str(product.id), str(donor.id), line_ids=[str(asking_line.id)]
        )

        marked = [row for row in detail["sales_orders"] if row["is_this_line"]]
        assert len(marked) == 1
        assert marked[0]["line_id"] == str(asking_line.id)
