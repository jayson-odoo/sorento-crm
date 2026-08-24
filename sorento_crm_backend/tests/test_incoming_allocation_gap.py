"""Incoming-stock allocation gap - `unallocated_quantity` on every allocation-bearing payload.

The signal answers "is this incoming quantity already claimed by a salesperson?".
Emitted as the GAP only (never the shipped base) so the privacy rule at the top of
`incoming_stock_service.py` holds: no consumer can derive `quantity_received`.

Semantics (identical across all three payload builders):
  * no allocations at all      -> None   (the empty `warehouse_allocations` list IS the signal)
  * allocated == quantity_shipped -> None   (fully allocated, nothing to flag)
  * allocated  < quantity_shipped -> int    (the unallocated remainder)
  * allocated  > quantity_shipped -> None   (over-allocated; clamp, never negative)

The base is `quantity_shipped`, NOT `remaining_incoming_quantity` - allocations are
not decremented as goods are received, so on a partially-received line the two
numbers have different bases. `test_*_partially_received_line_uses_shipped_base`
is the regression guard for that.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    SPOAllocation,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.incoming_stock_service import IncomingStockService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _product(db, code: str) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"CAT-{code}", category_name=f"Category {code}"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"UOM-{code}", uom_name="Each")
    db.add_all([category, uom])
    db.flush()

    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return pid


def _shipment(db, *, number: str, eta: date | None = date(2026, 2, 1)) -> str:
    sid = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=sid,
            shipment_number=number,
            shipment_date=date(2026, 1, 1),
            estimated_arrival_date=eta,
        )
    )
    db.flush()
    return sid


def _line(db, shipment_id: str, product_id: str, *, shipped: int, received: int = 0) -> None:
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=shipment_id,
            product_id=product_id,
            quantity_shipped=shipped,
            quantity_received=received,
            line_status="in_transit",
        )
    )
    db.flush()


def _warehouse(db, code: str) -> str:
    wid = str(uuid.uuid4())
    db.add(Warehouse(id=wid, warehouse_code=code, warehouse_name=f"{code} Warehouse"))
    db.flush()
    return wid


def _alloc(db, shipment_id: str, product_id: str, warehouse_id: str, qty: int, *, spo: str) -> None:
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()),
            spo_number=spo,
            inbound_shipment_id=shipment_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            allocated_quantity=qty,
        )
    )
    db.flush()


def _only_line(res: dict) -> dict:
    assert res["empty"] is False
    return res["data"][0]["lines"][0]


# ---------------------------------------------------------------- incoming_list
def test_list_no_allocation_emits_none(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    _line(db, s, p, shipped=100)
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert line["warehouse_allocations"] == []
    assert line["unallocated_quantity"] is None


def test_list_partial_allocation_emits_gap(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100)
    _alloc(db, s, p, w, 60, spo="SPO-1")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert line["remaining_incoming_quantity"] == 100
    assert line["unallocated_quantity"] == 40


def test_list_fully_allocated_emits_none(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100)
    _alloc(db, s, p, w, 100, spo="SPO-1")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert line["unallocated_quantity"] is None


def test_list_over_allocated_clamps_to_none(db):
    """Allocated beyond what shipped is a data error, not a negative gap."""
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100)
    _alloc(db, s, p, w, 120, spo="SPO-1")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert line["unallocated_quantity"] is None


def test_list_multi_warehouse_allocation_sums(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w1, w2 = _warehouse(db, "BRW"), _warehouse(db, "KLW")
    _line(db, s, p, shipped=100)
    _alloc(db, s, p, w1, 30, spo="SPO-1")
    _alloc(db, s, p, w2, 20, spo="SPO-2")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert sum(a["allocated_quantity"] for a in line["warehouse_allocations"]) == 50
    assert line["unallocated_quantity"] == 50


def test_list_partially_received_line_uses_shipped_base(db):
    """Regression guard: the gap must NOT be measured against remaining.

    shipped 100, received 60 -> remaining 40. Allocated 40 equals remaining, so a
    remaining-based rule would report "fully allocated". Against the shipped base
    60 units are still unclaimed.
    """
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100, received=60)
    _alloc(db, s, p, w, 40, spo="SPO-1")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    assert line["remaining_incoming_quantity"] == 40
    assert line["unallocated_quantity"] == 60


def test_list_never_exposes_the_shipped_base(db):
    """Privacy rule: shipped on the wire lets a consumer derive quantity_received."""
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100, received=60)
    _alloc(db, s, p, w, 40, spo="SPO-1")
    db.commit()

    line = _only_line(IncomingStockService(db).incoming_list(product_ids=[p]))
    for banned in ("quantity_shipped", "quantity_received", "quantity_rejected"):
        assert banned not in line


# ------------------------------------------------------------ incoming_for_product
def test_by_product_partial_allocation_emits_gap(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100, received=60)
    _alloc(db, s, p, w, 40, spo="SPO-1")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(product_ids=[p])
    ship = res["data"][0]["shipments"][0]
    assert ship["remaining_incoming_quantity"] == 40
    assert ship["unallocated_quantity"] == 60
    assert "quantity_shipped" not in ship


def test_by_product_no_allocation_emits_none(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    _line(db, s, p, shipped=100)
    db.commit()

    res = IncomingStockService(db).incoming_for_product(product_ids=[p])
    ship = res["data"][0]["shipments"][0]
    assert ship["warehouse_allocations"] == []
    assert ship["unallocated_quantity"] is None


# ------------------------------------------------------ shipment_incoming_products
def test_shipment_products_partial_allocation_emits_gap(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100, received=60)
    _alloc(db, s, p, w, 40, spo="SPO-1")
    db.commit()

    res = IncomingStockService(db).shipment_incoming_products(s)
    prod = res["data"]["products"][0]
    assert prod["remaining_incoming_quantity"] == 40
    assert prod["unallocated_quantity"] == 60
    assert "quantity_shipped" not in prod


def test_shipment_products_fully_allocated_emits_none(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1")
    w = _warehouse(db, "BRW")
    _line(db, s, p, shipped=100)
    _alloc(db, s, p, w, 100, spo="SPO-1")
    db.commit()

    res = IncomingStockService(db).shipment_incoming_products(s)
    assert res["data"]["products"][0]["unallocated_quantity"] is None
