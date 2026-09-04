"""AC-F4: `InboundShipmentUpdate` accepts `shipment_number`, and an unknown key 422s.

`shipment_number` used to be silently dropped by the PUT: it is not declared on
`InboundShipmentUpdate`, so `update_shipment`'s `exclude_unset` dump never saw it and
`setattr` never ran - the save returned 200 and the field never moved. The Container Status
workbook import is silently dropped exactly the same way if a key is mistyped, which is what
`extra="forbid"` now catches at the schema boundary before it ever reaches the service.

Postgres only, blank schema - CI's database has no data, so this seeds every FK target
itself rather than borrowing an existing row.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models.procurement import Supplier
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentUpdate
from app.services.procurement_service import InboundShipmentService
from tests._pg_fixture import blank_session

MARKER = "ZZSN"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _supplier(db) -> Supplier:
    s = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        supplier_name=f"{MARKER} supplier",
        is_active=True,
    )
    db.add(s)
    db.flush()
    return s


def _shipment(db, supplier):
    container = f"{MARKER}U{uuid.uuid4().hex[:7].upper()}"
    payload = InboundShipmentCreate(
        shipment_number=container,
        supplier_id=str(supplier.id),
        shipment_date=date(2026, 1, 1),
        shipping_container_number=container,
    )
    shipment = InboundShipmentService(db).create_shipment(payload)
    db.commit()
    return shipment


def test_shipment_number_is_declared_and_written_on_update(db):
    supplier = _supplier(db)
    shipment = _shipment(db, supplier)

    payload = InboundShipmentUpdate(shipment_number="RENAMED-0042")
    InboundShipmentService(db).update_shipment(str(shipment.id), payload, updated_by=None)
    db.commit()

    db.refresh(shipment)
    assert shipment.shipment_number == "RENAMED-0042"


def test_shipment_number_survives_the_json_round_trip(db):
    """The same rename, as it actually arrives - through the wire shape a PUT body takes,
    not a Python kwarg. `model_validate` on a dict is the same path FastAPI's body parsing
    takes; a field declared with the wrong alias or type would pass a kwarg test and still
    422 in production.
    """
    payload = InboundShipmentUpdate.model_validate({"shipment_number": "RENAMED-0099"})
    assert payload.shipment_number == "RENAMED-0099"
    assert "shipment_number" in payload.model_fields_set


def test_an_unknown_field_is_refused_rather_than_silently_dropped():
    """Extra keys used to validate fine and vanish - a save that looked like it worked."""
    with pytest.raises(ValidationError) as excinfo:
        InboundShipmentUpdate.model_validate({"seal_number": "J07", "made_up_field": "x"})

    errors = excinfo.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errors)
    assert any("made_up_field" in e["loc"] for e in errors)


def test_a_known_field_still_validates_alongside_the_forbid(db):
    """`extra='forbid'` refuses what it does not know - it does not refuse everything else."""
    supplier = _supplier(db)
    shipment = _shipment(db, supplier)

    payload = InboundShipmentUpdate.model_validate(
        {"seal_number": "J0713349", "shipper": "SHENZHEN XINDESHENG"}
    )
    InboundShipmentService(db).update_shipment(str(shipment.id), payload, updated_by=None)
    db.commit()

    db.refresh(shipment)
    assert shipment.seal_number == "J0713349"
    assert shipment.shipper == "SHENZHEN XINDESHENG"
