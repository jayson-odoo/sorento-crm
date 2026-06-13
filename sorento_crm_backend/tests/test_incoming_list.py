"""IncomingStockService.incoming_list — unified shipment-rooted incoming view.

One row per still-incoming shipment, each with nested product `lines[]` (no
aggregate totals). Covers: product filter narrows lines, shipment/eta filters,
required-narrower guard, and absence of aggregate fields.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    SPOAllocation,
)
from app.models.product import Product
from app.models.resources import Attachment
from app.services.incoming_stock_service import IncomingStockService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Product.__table__,
            Warehouse.__table__,
            Attachment.__table__,
            InboundShipment.__table__,
            InboundShipmentLine.__table__,
            SPOAllocation.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _product(db, code: str) -> str:
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=str(uuid.uuid4()),
            base_uom_id=str(uuid.uuid4()),
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return pid


def _shipment(db, *, number: str, eta: date | None, container: str | None = None) -> str:
    sid = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=sid,
            shipment_number=number,
            shipping_container_number=container,
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


def test_shipment_rooted_with_nested_lines(db):
    p1 = _product(db, "SKU-A")
    p2 = _product(db, "SKU-B")
    s = _shipment(db, number="SH1", eta=date(2026, 2, 1), container="CONT1")
    _line(db, s, p1, shipped=10)
    _line(db, s, p2, shipped=5)
    db.commit()

    res = IncomingStockService(db).incoming_list(shipment_ids=[s])
    assert res["empty"] is False
    assert len(res["data"]) == 1
    row = res["data"][0]
    assert row["shipment_number"] == "SH1"
    assert row["shipping_container_number"] == "CONT1"
    # Both products nested as lines; no aggregate total at shipment root.
    assert "total_remaining_incoming_quantity" not in row
    codes = sorted(l["product_code"] for l in row["lines"])
    assert codes == ["SKU-A", "SKU-B"]
    qtys = {l["product_code"]: l["remaining_incoming_quantity"] for l in row["lines"]}
    assert qtys == {"SKU-A": 10, "SKU-B": 5}


def test_product_filter_narrows_lines(db):
    p1 = _product(db, "SKU-A")
    p2 = _product(db, "SKU-B")
    s = _shipment(db, number="SH1", eta=date(2026, 2, 1))
    _line(db, s, p1, shipped=10)
    _line(db, s, p2, shipped=5)
    db.commit()

    res = IncomingStockService(db).incoming_list(product_ids=[p1])
    assert len(res["data"]) == 1
    lines = res["data"][0]["lines"]
    # Shipment is included because it carries SKU-A, but only that line shows.
    assert [l["product_code"] for l in lines] == ["SKU-A"]


def test_fully_received_line_excluded(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1", eta=date(2026, 2, 1))
    _line(db, s, p, shipped=10, received=10)  # nothing remaining
    db.commit()

    res = IncomingStockService(db).incoming_list(product_ids=[p])
    assert res["empty"] is True
    assert res["data"] == []


def test_eta_window_filters_shipments(db):
    p = _product(db, "SKU-A")
    s1 = _shipment(db, number="SH1", eta=date(2026, 2, 1))
    s2 = _shipment(db, number="SH2", eta=date(2026, 5, 1))
    _line(db, s1, p, shipped=3)
    _line(db, s2, p, shipped=4)
    db.commit()

    res = IncomingStockService(db).incoming_list(
        product_ids=[p], eta_from=date(2026, 4, 1)
    )
    assert [r["shipment_number"] for r in res["data"]] == ["SH2"]


def test_requires_a_narrowing_filter(db):
    p = _product(db, "SKU-A")
    s = _shipment(db, number="SH1", eta=date(2026, 2, 1))
    _line(db, s, p, shipped=3)
    db.commit()

    res = IncomingStockService(db).incoming_list()
    assert res["empty"] is True
    assert res["data"] == []
    assert "message" in res


def test_unresolved_product_returns_empty(db):
    res = IncomingStockService(db).incoming_list(product_ids=["NOPE-NOT-A-SKU"])
    assert res["empty"] is True
    assert res["data"] == []
