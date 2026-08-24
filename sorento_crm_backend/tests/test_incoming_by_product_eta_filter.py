"""IncomingStockService.incoming_for_product ETA window filter.

eta_from / eta_to (inclusive) narrow to shipments whose estimated_arrival_date
falls in the window. Applied on top of the product hint - never standalone.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.incoming_stock_service import IncomingStockService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a JSONB->JSON compiler shim and a hand-picked
    table list.
    """
    with blank_session() as s:
        yield s


def _product(db, code: str) -> str:
    """Seed a product plus the category and UOM its NOT NULL FKs demand.

    The sqlite version passed a fresh random uuid for category_id/base_uom_id,
    pointing at rows that did not exist. sqlite does not enforce foreign keys
    unless asked, so it accepted them; Postgres rejects the insert. Real parent
    rows are created here instead.
    """
    category_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.add(
        ProductCategory(
            id=category_id, category_code=f"CAT-{code}", category_name=f"Cat {code}"
        )
    )
    db.add(UnitOfMeasure(id=uom_id, uom_code=f"UOM-{code}", uom_name=f"Uom {code}"))
    db.flush()

    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=category_id,
            base_uom_id=uom_id,
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return pid


def _shipment_line(db, product_id: str, *, eta: date | None, number: str) -> None:
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
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=sid,
            product_id=product_id,
            quantity_shipped=10,
            quantity_received=0,
            line_status="in_transit",
        )
    )
    db.flush()


def _etas(result, product_code):
    bucket = next(b for b in result["data"] if b["product_code"] == product_code)
    return sorted(s["estimated_arrival_date"] for s in bucket["shipments"])


def test_eta_from_excludes_earlier_shipments(db):
    p = _product(db, "SKU-1")
    _shipment_line(db, p, eta=date(2026, 2, 1), number="S1")
    _shipment_line(db, p, eta=date(2026, 3, 15), number="S2")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(
        product_ids=[p], eta_from=date(2026, 3, 1)
    )
    assert _etas(res, "SKU-1") == [date(2026, 3, 15)]


def test_eta_to_excludes_later_shipments(db):
    p = _product(db, "SKU-2")
    _shipment_line(db, p, eta=date(2026, 2, 1), number="S1")
    _shipment_line(db, p, eta=date(2026, 3, 15), number="S2")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(
        product_ids=[p], eta_to=date(2026, 2, 28)
    )
    assert _etas(res, "SKU-2") == [date(2026, 2, 1)]


def test_eta_window_inclusive_bounds(db):
    p = _product(db, "SKU-3")
    _shipment_line(db, p, eta=date(2026, 2, 1), number="S1")
    _shipment_line(db, p, eta=date(2026, 2, 15), number="S2")
    _shipment_line(db, p, eta=date(2026, 3, 1), number="S3")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(
        product_ids=[p], eta_from=date(2026, 2, 1), eta_to=date(2026, 3, 1)
    )
    assert _etas(res, "SKU-3") == [date(2026, 2, 1), date(2026, 2, 15), date(2026, 3, 1)]


def test_eta_filter_drops_product_with_no_match_in_window(db):
    p = _product(db, "SKU-4")
    _shipment_line(db, p, eta=date(2026, 1, 10), number="S1")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(
        product_ids=[p], eta_from=date(2026, 6, 1)
    )
    assert res["empty"] is True
    assert res["data"] == []


def test_no_eta_returns_all_shipments(db):
    p = _product(db, "SKU-5")
    _shipment_line(db, p, eta=date(2026, 2, 1), number="S1")
    _shipment_line(db, p, eta=None, number="S2")
    db.commit()

    res = IncomingStockService(db).incoming_for_product(product_ids=[p])
    bucket = next(b for b in res["data"] if b["product_code"] == "SKU-5")
    etas = {s["estimated_arrival_date"] for s in bucket["shipments"]}
    assert etas == {None, date(2026, 2, 1)}
