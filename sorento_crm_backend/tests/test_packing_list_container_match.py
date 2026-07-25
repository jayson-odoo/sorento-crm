"""InboundShipmentService.create_shipment — container-number upsert matching.

The external packing-list API (n8n) creates inbound shipments. Container number
is the shipment's secondary identifier: when no shipment_number matches, an
existing *not fully received* shipment carrying the same container is updated in
place (header + lines + attachment) instead of creating a duplicate. A container
whose shipment is already fully received/completed is free to carry a new one.
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
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    SPOAllocation,
    PickingHeader,
    PickingLine,
)
from app.models.product import Product
from app.models.resources import Attachment
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate
from app.services.procurement_service import InboundShipmentService


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
            Attachment.__table__,
            InboundShipment.__table__,
            InboundShipmentLine.__table__,
            SPOAllocation.__table__,
            PickingHeader.__table__,
            PickingLine.__table__,
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


def _attachment(db) -> str:
    aid = str(uuid.uuid4())
    db.add(
        Attachment(
            id=aid,
            original_filename=f"{aid}.pdf",
            stored_filename=f"{aid}.pdf",
            file_path=f"/tmp/{aid}.pdf",
            mime_type="application/pdf",
            file_size_bytes=1,
        )
    )
    db.flush()
    return aid


def _create(db, product_id, **header):
    header.setdefault("shipment_date", date(2026, 1, 1))
    lines = header.pop("lines", [(product_id, 5)])
    payload = InboundShipmentCreate(
        shipment_lines=[
            InboundShipmentLineCreate(product_id=pid, quantity_shipped=qty)
            for pid, qty in lines
        ],
        **header,
    )
    return InboundShipmentService(db).create_shipment(payload)


def test_container_match_updates_not_fully_received_in_place(db):
    p = _product(db, "SKU-A")
    att1 = _attachment(db)
    att2 = _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="CONT-1",
        attachment_id=att1,
        lines=[(p, 5)],
    )
    db.commit()

    # No shipment_number on either payload — match must fall through to container.
    second = _create(
        db,
        p,
        shipping_container_number="CONT-1",
        attachment_id=att2,
        shipment_number="SH-NEW",
        lines=[(p, 9)],
    )
    db.commit()

    # Same row reused (update-in-place), not a new shipment.
    assert second.id == first.id
    assert getattr(second, "_already_existed", False) is True
    assert db.query(InboundShipment).count() == 1
    # Attachment replaced with the n8n request payload's attachment_id.
    assert second.attachment_id == att2
    # Shipment number filled in, lines replaced (not summed across calls).
    assert second.shipment_number == "SH-NEW"
    assert sum(l.quantity_shipped for l in second.shipment_lines) == 9


def test_fully_received_container_does_not_match_creates_new(db):
    """A received container is free to carry a NEW shipment.

    The new shipment must differ on the identity triple (container, ETA,
    shipment_date) — an identical triple means the same packing list was
    uploaded twice and is rejected instead. See
    tests/test_packing_list_duplicate_detection.py.
    """
    p = _product(db, "SKU-A")
    att1 = _attachment(db)
    att2 = _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="CONT-9",
        shipment_date=date(2026, 1, 1),
        attachment_id=att1,
        lines=[(p, 5)],
    )
    # Mark it fully received (line receipts drive this in real usage; set the
    # terminal status directly so the container is free to carry a new shipment).
    first.shipment_status = "fully_received"
    db.commit()

    # Genuine reuse: same container, later voyage.
    second = _create(
        db,
        p,
        shipping_container_number="CONT-9",
        shipment_date=date(2026, 5, 20),
        attachment_id=att2,
        lines=[(p, 3)],
    )
    db.commit()

    # The received shipment is free to reuse the container → a brand new row.
    assert second.id != first.id
    assert db.query(InboundShipment).count() == 2


def test_shipment_number_takes_precedence_over_container(db):
    p = _product(db, "SKU-A")
    att1 = _attachment(db)
    att2 = _attachment(db)
    db.commit()

    a = _create(db, p, shipment_number="SH-1", shipping_container_number="CONT-A", attachment_id=att1)
    b = _create(db, p, shipment_number="SH-2", shipping_container_number="CONT-B", attachment_id=att2)
    db.commit()
    assert a.id != b.id
    assert db.query(InboundShipment).count() == 2

    # Re-send SH-1 with a different container: matches by shipment_number, updates row a.
    again = _create(db, p, shipment_number="SH-1", shipping_container_number="CONT-Z")
    db.commit()
    assert again.id == a.id
    assert again.shipping_container_number == "CONT-Z"
    assert db.query(InboundShipment).count() == 2
