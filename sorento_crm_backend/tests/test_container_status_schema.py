"""Container status schema (slice 1): clearance columns + the observation ledger.

Four things are worth pinning, and each has already gone wrong somewhere in this
repo:

1. **Migration / model parity.** A column added to one and not the other is the
   failure that broke `user_sessions.id` on production. `create_all` builds the
   test schema from the MODEL, so a blank-schema test alone would pass happily
   while the migration was missing a column - the parity assertion is what makes
   the migration itself the thing under test.
2. **Backend / frontend contract parity.** The frontend prototype was signed off
   against `ClearanceFields`. If the model and that interface drift, the field
   silently never reaches the UI.
3. **Observations never touch the shipment (AC E2).** The whole justification for
   an append-only ledger is that integration values do not overwrite human ones.
4. **`__audit_track__`** is what replaces a revisions table (D5). Without it every
   ETA revision is lost.

Postgres only, blank scratch schema, all writes rolled back.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.procurement import (
    InboundShipment,
    ShipmentTrackingObservation,
    Supplier,
)
from tests._pg_fixture import blank_session, unique_code


# The 21 fields the sheet contributes. Written out by hand ON PURPOSE: deriving
# this list from the model or the migration would make the parity tests below
# tautological.
#: The columns migration 311 ADDS. `estimated_arrival_date` is deliberately not
#: here: it already existed on inbound_shipments, and the workbook ETA writes to
#: it rather than to a second column of its own (see migration 314).
CLEARANCE_COLUMNS = {
    "loc",
    "liner_code",
    "china_forwarder",
    "malaysia_forwarder",
    "consignee",
    "free_days_available",
    "stacked",
    "loading_date",
    "etc_date",
    "etd_date",
    "eta_delay_date",
    "inspection_date",
    "approval_date",
    "gatepass_date",
    "delivery_warehouse",
    "warehouse_arrival_date",
    "informed_collection_date",
    "collection_date",
    "coa_permit_no",
    "source_sheet",
}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _load_migration():
    """Import the migration module by path - `311_...` is not a valid identifier."""
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "311_container_status_columns.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_311", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _shipment(db, *, container: str) -> InboundShipment:
    """A shipment with its real supplier parent. Postgres enforces the FK."""
    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP"),
        supplier_name="ZZT Container Status Supplier",
    )
    db.add(supplier)
    db.flush()

    shipment = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHP"),
        supplier_id=supplier.id,
        shipment_date=date(2026, 7, 1),
        shipping_container_number=container,
    )
    db.add(shipment)
    db.flush()
    return shipment


# ---------------------------------------------------------------- parity


def test_migration_adds_exactly_the_clearance_columns():
    """The migration's column list is the clearance set, no more and no less."""
    module = _load_migration()
    from_migration = (
        {name for name, _type in module._TEXT_COLUMNS}
        | set(module._DATE_COLUMNS)
        | {"free_days_available"}
    )
    assert from_migration == CLEARANCE_COLUMNS


def test_model_carries_every_migrated_column_with_a_matching_type():
    """Model and migration agree on names AND on date-vs-text-vs-int.

    A `Date` column declared as `String` on the model reads back a string and
    every date comparison downstream silently becomes lexical.
    """
    module = _load_migration()
    model_columns = InboundShipment.__table__.columns

    for name in CLEARANCE_COLUMNS:
        assert name in model_columns, f"{name} is in the migration but not the model"

    for name in module._DATE_COLUMNS:
        assert isinstance(model_columns[name].type, sa.Date), f"{name} must be a Date"
    for name, type_ in module._TEXT_COLUMNS:
        assert isinstance(model_columns[name].type, sa.String), f"{name} must be a String"
        assert model_columns[name].type.length == type_.length, f"{name} length differs"
    assert isinstance(model_columns["free_days_available"].type, sa.Integer)


def test_model_matches_the_frontend_clearance_contract():
    """The signed-off Phase 1 contract and the model are the same field set.

    Slice 3 wires the real API onto the prototype's hooks. A field present on one
    side only does not fail loudly - it just never appears in the UI.
    """
    types_file = (
        Path(__file__).resolve().parents[2]
        / "sorento_crm_frontend"
        / "app"
        / "(protected)"
        / "procurement-management"
        / "packing-lists"
        / "types"
        / "packingList.types.ts"
    )
    if not types_file.exists():  # pragma: no cover - frontend absent in some checkouts
        pytest.skip("frontend types file not present in this checkout")

    source = types_file.read_text()
    block = re.search(
        r"export interface ClearanceFields \{(.*?)\n\}", source, re.S
    )
    assert block, "ClearanceFields interface not found - was it renamed?"
    frontend_fields = set(re.findall(r"^\s{2}(\w+)\?:", block.group(1), re.M))

    assert frontend_fields == CLEARANCE_COLUMNS


def test_audit_track_is_enabled():
    """Without this, an ETA revision leaves no trace anywhere (D5)."""
    assert InboundShipment.__audit_track__ is True


# ---------------------------------------------------------------- behaviour


def test_clearance_columns_start_null_on_an_existing_shipment(db):
    """The DDL must not disturb rows that predate the container status feature."""
    shipment = _shipment(db, container="ZZTU0000001")
    db.expire(shipment)

    for name in sorted(CLEARANCE_COLUMNS):
        assert getattr(shipment, name) is None, f"{name} should default to NULL"


def test_observation_ledger_records_multiple_values_for_one_field(db):
    """Append-only means a revised ETA adds a row, it does not replace one."""
    shipment = _shipment(db, container="ZZTU0000002")

    for day, fetched in ((8, 1), (12, 5)):
        db.add(
            ShipmentTrackingObservation(
                id=str(uuid.uuid4()),
                shipment_id=shipment.id,
                field_key="eta_delay_date",
                observed_value=f"2026-07-{day:02d}",
                source="liner_cma",
                source_ref="ZZT-booking-1",
                observed_at=datetime(2026, 7, day, 3, 0),
                fetched_at=datetime(2026, 7, fetched, 3, 0),
            )
        )
    db.flush()

    rows = (
        db.query(ShipmentTrackingObservation)
        .filter(ShipmentTrackingObservation.shipment_id == shipment.id)
        .order_by(ShipmentTrackingObservation.fetched_at.desc())
        .all()
    )
    assert [r.observed_value for r in rows] == ["2026-07-12", "2026-07-08"]


def test_observation_ingest_leaves_the_shipment_byte_identical(db):
    """AC E2. This is the guardrail the user asked for by name.

    An integration may only ever add evidence. If a future adapter starts writing
    to the shipment, this fails.
    """
    shipment = _shipment(db, container="ZZTU0000003")
    shipment.eta_delay_date = date(2026, 7, 20)
    shipment.inspection_date = None
    db.flush()

    tracked = [c.name for c in InboundShipment.__table__.columns]
    before = {name: getattr(shipment, name) for name in tracked}

    for field, value in (
        ("eta_delay_date", "2026-07-08"),
        ("inspection_date", "2026-07-09"),
    ):
        db.add(
            ShipmentTrackingObservation(
                id=str(uuid.uuid4()),
                shipment_id=shipment.id,
                field_key=field,
                observed_value=value,
                source="cidb_epermit",
            )
        )
    db.flush()
    db.expire(shipment)

    after = {name: getattr(shipment, name) for name in tracked}
    assert after == before
    # And specifically: the feed disagreed with the human, and the human won.
    assert shipment.eta_delay_date == date(2026, 7, 20)
    assert shipment.inspection_date is None


def test_unsupported_carrier_is_recordable(db):
    """A carrier with no adapter must be visible as a gap, not silently absent."""
    shipment = _shipment(db, container="ZZTU0000004")
    db.add(
        ShipmentTrackingObservation(
            id=str(uuid.uuid4()),
            shipment_id=shipment.id,
            field_key="eta_delay_date",
            observed_value=None,
            source="unsupported",
            source_ref="NSS",
        )
    )
    db.flush()

    row = (
        db.query(ShipmentTrackingObservation)
        .filter(ShipmentTrackingObservation.shipment_id == shipment.id)
        .one()
    )
    assert row.source == "unsupported"
    assert row.observed_value is None
    assert row.fetched_at is not None


def test_observations_are_removed_with_their_shipment(db):
    """ON DELETE CASCADE - a deleted packing list must not leave orphan evidence."""
    shipment = _shipment(db, container="ZZTU0000005")
    shipment_id = shipment.id
    db.add(
        ShipmentTrackingObservation(
            id=str(uuid.uuid4()),
            shipment_id=shipment_id,
            field_key="gatepass_date",
            observed_value="2026-07-17",
            source="liner_oocl",
        )
    )
    db.flush()

    db.execute(
        sa.text("DELETE FROM inbound_shipments WHERE id = :i"), {"i": shipment_id}
    )
    db.flush()

    remaining = (
        db.query(ShipmentTrackingObservation)
        .filter(ShipmentTrackingObservation.shipment_id == shipment_id)
        .count()
    )
    assert remaining == 0
