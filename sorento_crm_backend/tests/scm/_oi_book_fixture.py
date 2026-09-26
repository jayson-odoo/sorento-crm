"""Shared book-building helpers for the S4 (importer pairing by date order, never drop) red
tests: `documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` S4, UAC
`board-received-stock-own-arrival-acceptance-criteria.md` AC-S4-1 to AC-S4-4.

Imports the seeded `World` / `world` / `sheet` from
`tests/test_project_order_inquiry_import_migration.py` rather than copying them - the same
convention every sibling importer test file in this domain (`test_oi_sheet_pairing_repair.py`,
`test_oi_sheet_date_follow_sheet.py`, ...) already uses, so the seeded world cannot drift.

Postgres only (`tests/_pg_fixture.py`, via `world()`). Every FK is seeded through `World`;
nothing here reads an existing row.
"""
from __future__ import annotations

from datetime import date
from typing import List, Tuple

from tests.test_project_order_inquiry_import_migration import World, sheet


def open_lines(w: World, order, dates: List[date], *, qty_ordered: str = "100"):
    """One OPEN sales-order line per date, all sharing `w`'s own product/warehouse so every
    line is a genuine candidate for every sheet row built by `book_of` below - the ambiguity
    R4's date-order pairing has to resolve, rather than the item/location filters resolving
    it before the line pick ever runs. `qty_ordered` defaults large enough that several
    sheet rows can land on the same line (AC-S4-2's "second row" shape) without ever
    tripping `qty_exceeds_ordered`.
    """
    return [w.line(order, qty_ordered=qty_ordered, required_date=d) for d in dates]


def book_of(w: World, order, rows: List[Tuple[int, date]]) -> bytes:
    """One tab, `rows` as `[(qty, delivery_date), ...]`, all against `w`'s own product and
    warehouse (so the location/item filters never themselves decide the line - only the
    date-order pairing this slice is red for does)."""
    return sheet([
        (order.so_number, w.product.product_code, qty, delivery_date,
         w.warehouse.warehouse_code, "")
        for qty, delivery_date in rows
    ])
