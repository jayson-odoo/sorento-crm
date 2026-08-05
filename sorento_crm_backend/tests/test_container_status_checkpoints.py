"""Clearance checkpoints as configurable status rows (slice 2).

`inbound_shipment` is the first status entity registered in this repo, and it
registers a **timeline of independent checkpoints**, not a single-position graph.
That distinction is the thing worth pinning:

* A container reaches whichever checkpoints its dates say it reached, in any
  combination. The real workbook has containers with a gatepass and no inspection.
  There is deliberately no `status_id` column, so nothing can imply that reaching a
  later checkpoint completed the earlier ones.
* The checkpoint LIST is data, not code. Renaming, reordering, recolouring or
  hiding one must be an admin edit, and `key` must stay welded to its
  `inbound_shipments` column so a rename cannot break the link.

The seeding is tested by running the migration's own `upgrade()`, not by asserting
against whatever the local database happens to contain.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.procurement import InboundShipment, Supplier
from app.models.status import Status
from app.status_engine.entities.inbound_shipment import (
    ENTITY_TYPE,
    count_records,
    migrate_records,
    register,
)
from app.status_engine.registry import get_status_entity
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "312_container_status_checkpoints.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_312", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _seed_checkpoints(db) -> None:
    """Run the migration's own INSERTs against the scratch schema.

    Importing the migration and executing its statements is what makes the
    MIGRATION the thing under test - asserting against the live `statuses` table
    would test the local database instead, and CI's is empty.
    """
    module = _load_migration()
    for index, (key, label, category, caption, colour) in enumerate(module.CHECKPOINTS):
        db.add(
            Status(
                id=str(uuid.uuid4()),
                entity_type=ENTITY_TYPE,
                key=key,
                category=category,
                label=label,
                color_hex=colour,
                description=caption,
                sort_order=(index + 1) * 10,
            )
        )
    db.flush()


def _shipment(db, container: str, **dates) -> InboundShipment:
    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP"),
        supplier_name="ZZT Checkpoint Supplier",
    )
    db.add(supplier)
    db.flush()
    shipment = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHP"),
        supplier_id=supplier.id,
        shipment_date=date(2026, 7, 1),
        shipping_container_number=container,
        **dates,
    )
    db.add(shipment)
    db.flush()
    return shipment


# ------------------------------------------------------------------ definition


def test_the_seeded_checkpoints_map_onto_real_shipment_columns():
    """A typo in a key would silently produce a checkpoint nothing can ever reach."""
    module = _load_migration()
    columns = InboundShipment.__table__.columns

    assert len(module.CHECKPOINTS) == 11
    for key, label, category, caption, colour in module.CHECKPOINTS:
        assert key in columns, f"{key} is not a column on inbound_shipments"
        assert isinstance(columns[key].type, sa.Date), f"{key} must be a date"
        assert label and caption
        assert category in ("origin", "sea", "clearance", "delivery")
        assert colour.startswith("#")


def test_the_seed_order_is_the_real_chain():
    """Timeline order is the physical order the container actually moves in."""
    module = _load_migration()
    assert [key for key, *_ in module.CHECKPOINTS] == [
        "loading_date",
        "etc_date",
        "etd_date",
        "eta_date",
        "eta_delay_date",
        "inspection_date",
        "approval_date",
        "gatepass_date",
        "warehouse_arrival_date",
        "informed_collection_date",
        "collection_date",
    ]


def test_the_four_unmaintained_fields_are_not_checkpoints():
    """ATA, ORI DOC, K1 and YARD are filled 6/4/4/4 times out of 407. They stay on
    the record for round-tripping, but a timeline of eleven mostly-blank dots would
    be worse than useless (B7)."""
    module = _load_migration()
    keys = {key for key, *_ in module.CHECKPOINTS}
    for dead in (
        "ata_date",
        "ori_doc_received_date",
        "k1_submission_date",
        "yard_arrival_date",
    ):
        assert dead not in keys


def test_no_checkpoint_is_initial_or_terminal_or_system():
    """A checkpoint timeline has no single position, so no row may claim to be the
    start or the end. And nothing is `is_system`, because the point of the exercise
    is that purchasing can edit this list themselves."""
    module = _load_migration()
    source = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "312_container_status_checkpoints.py"
    ).read_text()
    assert "false, false, true, false, false, false" in source
    assert len(module.CHECKPOINTS) == 11


def test_seeding_twice_does_not_duplicate_or_overwrite(db):
    """An admin's renamed label and reordered checkpoint must survive a re-deploy."""
    _seed_checkpoints(db)

    row = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "gatepass_date")
        .one()
    )
    row.label = "Released from port"
    row.sort_order = 5
    db.flush()

    # The migration's guard: only keys that are missing get inserted.
    existing = {
        k for (k,) in db.query(Status.key).filter(Status.entity_type == ENTITY_TYPE)
    }
    module = _load_migration()
    to_insert = [c for c in module.CHECKPOINTS if c[0] not in existing]
    assert to_insert == []

    db.expire(row)
    assert row.label == "Released from port"
    assert row.sort_order == 5


# ------------------------------------------------------------------- registry


def test_the_entity_registers_and_carries_no_status_column():
    register()
    entity = get_status_entity(ENTITY_TYPE)

    assert entity is not None
    assert entity.model is InboundShipment
    assert entity.record_label_attr == "shipping_container_number"
    # The engine's default status attribute must NOT exist on this model: a
    # checkpoint timeline has no single current status, and a column implying one
    # would be a lie the first time a container skips a stage.
    assert "status_id" not in InboundShipment.__table__.columns


def test_count_records_counts_containers_that_reached_the_checkpoint(db):
    """What the admin sees before deleting a checkpoint."""
    _seed_checkpoints(db)
    gatepass = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "gatepass_date")
        .one()
    )
    inspection = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "inspection_date")
        .one()
    )

    _shipment(db, "ZZTU1000001", gatepass_date=date(2026, 7, 17))
    _shipment(db, "ZZTU1000002", gatepass_date=date(2026, 7, 18))
    _shipment(db, "ZZTU1000003")

    assert count_records(db, gatepass.id) == 2
    assert count_records(db, inspection.id) == 0


def test_a_container_can_reach_a_later_checkpoint_without_an_earlier_one(db):
    """The whole reason this is a checkpoint timeline. The real workbook does this:
    a gatepass with no inspection recorded."""
    _seed_checkpoints(db)
    gatepass = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "gatepass_date")
        .one()
    )
    inspection = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "inspection_date")
        .one()
    )

    shipment = _shipment(db, "ZZTU1000004", gatepass_date=date(2026, 7, 17))

    assert count_records(db, gatepass.id) == 1
    assert count_records(db, inspection.id) == 0
    assert shipment.inspection_date is None
    assert shipment.gatepass_date == date(2026, 7, 17)


def test_count_records_is_zero_for_a_checkpoint_with_no_backing_column(db):
    """An admin can create a status by hand whose key is not a date column. It must
    read as unreachable rather than raise."""
    db.add(
        Status(
            id=str(uuid.uuid4()),
            entity_type=ENTITY_TYPE,
            key="not_a_column",
            label="Invented",
            sort_order=999,
        )
    )
    db.flush()
    invented = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY_TYPE, Status.key == "not_a_column")
        .one()
    )

    assert count_records(db, invented.id) == 0


def test_migrating_records_between_checkpoints_does_nothing(db):
    """Moving every container's gatepass onto its inspection date would be
    corruption, not a migration."""
    _seed_checkpoints(db)
    rows = db.query(Status).filter(Status.entity_type == ENTITY_TYPE).limit(2).all()
    shipment = _shipment(db, "ZZTU1000005", gatepass_date=date(2026, 7, 17))

    assert migrate_records(db, rows[0].id, rows[1].id) == 0
    db.expire(shipment)
    assert shipment.gatepass_date == date(2026, 7, 17)
