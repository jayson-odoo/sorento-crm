"""#1362: the own-arrival credit ledger is per (product, bin), never per bin alone.

Owner (29 Sep 2026): SO382618's SRT357 line, 100 landed for it on SPO-2026/06-0152 at
BRW-BB (on hand 261), was credited 40 "landed for this line" and the rest sent to the BRW
pool, then the confirm guard refused the line on that same 40. Another product's credit at
the same bin had eaten SRT357's own-arrival allowance.

The reproduction: ONE sales order, TWO products, each with its own PO line converted to an
SPO and fully received at the SAME bin, both lines open, walked in the board's own order.
The second product must be credited min(its landed, its need, its own on hand), whatever
the first product's credit drew off the bin. A competing order of each product drives the
group net far below zero, so nothing but the credit can cover either line: any shortfall in
the credit shows up as a Buy.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests._pg_fixture import blank_session
from tests.test_fulfilment_board import TODAY, _cell, _line, _product, _service, _uid
from tests.test_fulfilment_board import _stock as _board_stock
from tests.scm._own_arrival_fixture import (
    order_with_lines,
    own_arrival_group,
    own_arrival_warehouse,
    po_line_bought_for,
    supplier_and_po,
)

FIRST_REQUIRED = date(2026, 8, 20)
SECOND_REQUIRED = date(2026, 8, 27)


def _own_arrival_reserved(contribution: dict) -> Decimal:
    return sum(
        (
            Decimal(s["qty"])
            for s in contribution["sources"]
            if s.get("rung") == "group_take" and s.get("source") == "own_arrival"
        ),
        Decimal("0"),
    )


def _buy_qty(contribution: dict) -> Decimal:
    return sum(
        (Decimal(s["qty"]) for s in contribution["sources"] if s.get("kind") == "buy"),
        Decimal("0"),
    )


def _own_step(contribution: dict) -> dict:
    return next(s for s in contribution["trail"] if s["kind"] == "own")


def _two_products_one_bin(db):
    """Product A: on hand 150, line 150 due first, 150 landed for it. Product B: on hand
    100, line 100 due a week later, 100 landed for it on its own SPO. Same order, same bin.
    Walking A first, a bin-keyed ledger leaves B with nothing (or at most B's on hand less
    A's 150)."""
    group, product_a = own_arrival_group(db)
    product_b = _product(db, f"ZZT-{_uid()[:8]}")
    own = own_arrival_warehouse(db, group)
    _board_stock(db, product_a, own, on_hand=150)
    _board_stock(db, product_b, own, on_hand=100)
    order, (line_a,) = order_with_lines(
        db, product=product_a, warehouse=own,
        lines=[{"qty": "150", "required_date": FIRST_REQUIRED, "source_ref": "LA"}],
    )
    line_b = _line(
        db, order, product_b, qty="100", required_date=SECOND_REQUIRED, warehouse=own,
    )
    line_b.source_ref = "LB"
    db.flush()
    po_a = supplier_and_po(db, po_number="ZZT-PO-1362A")
    po_line_bought_for(
        db, po_a, product_a, own, from_so_line_ref="LA", qty_received=150,
        spo_number="SPO-2026/06-0151",
    )
    po_b = supplier_and_po(db, po_number="ZZT-PO-1362B")
    po_line_bought_for(
        db, po_b, product_b, own, from_so_line_ref="LB", qty_received=100,
        spo_number="SPO-2026/06-0152",
    )
    # Competing earlier demand of BOTH products at the same bin: each group net goes far
    # negative, so the ordinary group take offers nothing and only the credit can cover.
    for product in (product_a, product_b):
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )
    return order, product_a, product_b, own


def test_1362_second_product_at_the_same_bin_is_credited_its_own_landed_goods_in_full():
    """#1362 regression pin: product B is credited min(100 landed, 100 needed, 100 on hand)
    = 100, not what product A's 150 credit left of a bin-wide counter."""
    with blank_session() as db:
        order, product_a, product_b, own = _two_products_one_bin(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        first = _cell(board, product_a.product_code, "2026-08-17")["contributions"][0]
        assert _own_arrival_reserved(first) == Decimal("150"), first["sources"]

        second = _cell(board, product_b.product_code, "2026-08-24")["contributions"][0]
        assert _own_arrival_reserved(second) == Decimal("100"), second["sources"]
        assert _buy_qty(second) == Decimal("0"), second["sources"]


def test_1362_the_sentence_states_what_landed_and_what_is_free_apart():
    """#1362 sentence: what landed on the shipment and how much of it is still free at the
    bin and taken first are two facts, said apart."""
    with blank_session() as db:
        order, _product_a, product_b, own = _two_products_one_bin(db)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        second = _cell(board, product_b.product_code, "2026-08-24")["contributions"][0]
        why = _own_step(second)["why"]
        assert (
            f"100 landed for this line on SPO-2026/06-0152; 100 free at "
            f"{own.warehouse_code}, taken first." in why
        ), why


def test_1362_free_part_smaller_than_landed_says_both_numbers():
    """When the bin holds less of the product than landed for the line, the sentence says
    both: 100 landed, 60 free, 60 taken first."""
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=60)
        order, _lines = order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "100", "required_date": FIRST_REQUIRED, "source_ref": "LX"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-1362X")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref="LX", qty_received=100,
            spo_number="SPO-2026/06-0153",
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, "2026-08-17")["contributions"][0]
        assert _own_arrival_reserved(contribution) == Decimal("60"), contribution["sources"]
        why = _own_step(contribution)["why"]
        assert (
            f"100 landed for this line on SPO-2026/06-0153; 60 free at "
            f"{own.warehouse_code}, taken first." in why
        ), why
