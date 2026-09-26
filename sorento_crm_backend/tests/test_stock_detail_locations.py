"""`FulfilmentBoardService.stock_detail`'s own `locations` field, in isolation.

Reviewer 10 (`PLAN-oi-request-cs-reserve.md` 3.9, section 6 verify item 2): the OI stock
grid (`OrderInquiryStockGrid.tsx`) reuses `CellStockTable`, the SAME per-location matrix
`stock_detail` already builds for the board's own cell dialog - `locations` is that
matrix. `test_fulfilment_board.py` already exercises this endpoint at length (its own
`test_the_drill_down_reads_a_whole_ownership_group_when_asked_for_one` /
`test_one_bin_still_reads_one_bin` cover `bins`, totals and the sales-order rows), but
neither asserts `locations` itself - the one field this new caller actually renders. This
file's own fixtures mirror `test_fulfilment_board.py`'s (`_product`/`_warehouse`/`_stock`)
rather than importing them, so it can seed the minimal chain `locations` alone needs.

Postgres, blank scratch schema, every FK target seeded here - CI's database is empty.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure

from ._pg_fixture import blank_session

MARKER = "zzt-stock-detail-locations"


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=code, product_name=f"{MARKER} {code}",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project", fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, *, on_hand: int) -> Stock:
    row = Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=on_hand, quantity_reserved=0,
    )
    db.add(row)
    db.flush()
    return row


def _service(db):
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    return FulfilmentBoardService(db)


def test_a_one_bin_read_locations_is_own_with_no_net():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        warehouse = _warehouse(db, f"ZZT{_uid()[:4]}")
        _stock(db, product, warehouse, on_hand=40)

        detail = _service(db).stock_detail(str(product.id), str(warehouse.id))

        assert len(detail["locations"]) == 1, detail["locations"]
        entry = detail["locations"][0]
        assert entry["where"] == "own", entry
        assert entry["location"] == warehouse.warehouse_code, entry
        assert "net" not in entry, entry
        assert "net_of" not in entry, entry


def test_a_group_read_locations_is_one_entry_per_member_bin_summing_to_the_total():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        first = _warehouse(db, f"ZZA{_uid()[:4]}-QQ")
        second = _warehouse(db, f"ZZB{_uid()[:4]}-QQ")
        outside = _warehouse(db, f"ZZC{_uid()[:4]}-RR")
        _stock(db, product, first, on_hand=100)
        _stock(db, product, second, on_hand=20)
        _stock(db, product, outside, on_hand=500)

        detail = _service(db).stock_detail(str(product.id), None, group="QQ")

        assert {entry["location"] for entry in detail["locations"]} == {
            first.warehouse_code, second.warehouse_code,
        }, detail["locations"]
        for entry in detail["locations"]:
            assert entry["where"] == "group", entry
            assert entry["net_of"] == "QQ", entry

        total_on_hand = sum(Decimal(entry["qty_on_hand"]) for entry in detail["locations"])
        assert total_on_hand == Decimal(detail["qty_on_hand"]) == Decimal("120"), (
            total_on_hand, detail["qty_on_hand"],
        )
