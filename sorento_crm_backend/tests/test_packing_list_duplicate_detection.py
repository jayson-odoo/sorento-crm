"""Packing-list duplicate detection after GRN.

Context (see documentation/plans/PLAN-packing-list-duplicate-detection.md):

A container is reusable — once its shipment is fully received it may carry a new
one, so container matching deliberately skipped received shipments and let a new
shipment be created. That left a hole: a user who mistakenly re-uploads the SAME
packing-list PDF after GRN silently gets a duplicate inbound shipment, because
packing-list PDFs carry no shipment_number for the primary guard to catch.

The rule: among shipments sharing a container, a *received* one whose
(container, ETA, shipment_date) triple equals the incoming payload is the same
packing list uploaded twice -> reject. Any difference in ETA or shipment date
means the container is genuinely carrying a new shipment -> create.

NULL semantics are `IS NOT DISTINCT FROM`: NULL==NULL is equal, NULL vs a value
is not.

Fixtures run on an in-memory sqlite engine — nothing here can touch the local
prod-copy database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.integration import IntegrationLog
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
from app.services.procurement_service import (
    DuplicatePackingListError,
    InboundShipmentService,
)


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
            IntegrationLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ---- helpers ---------------------------------------------------------------


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
    header.setdefault("shipment_date", date(2026, 6, 1))
    lines = header.pop("lines", [(product_id, 5)])
    payload = InboundShipmentCreate(
        shipment_lines=[
            InboundShipmentLineCreate(product_id=pid, quantity_shipped=qty)
            for pid, qty in lines
        ],
        **header,
    )
    return InboundShipmentService(db).create_shipment(payload)


def _received(db, shipment, status: str = "fully_received"):
    """Drive a shipment to a terminal received status (GRN does this for real)."""
    shipment.shipment_status = status
    db.commit()
    return shipment


# ---- 1/2: exact duplicate after GRN is rejected ----------------------------


@pytest.mark.parametrize("terminal_status", ["fully_received", "completed"])
def test_exact_triple_match_on_received_shipment_is_rejected(db, terminal_status):
    """Case 1 + 2 — the bug being fixed.

    Same container, same ETA, same shipment date, previous one already received:
    this is the same packing list uploaded twice. Reject, create nothing.
    """
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
    )
    _received(db, first, terminal_status)

    with pytest.raises(DuplicatePackingListError) as exc:
        _create(
            db,
            p,
            shipping_container_number="TEMU1234567",
            shipment_date=date(2026, 6, 1),
            estimated_arrival_date=date(2026, 6, 20),
            attachment_id=att2,
        )

    assert exc.value.error_code == "DUPLICATE_PACKING_LIST"
    # Message must name the container + both dates so the user can identify it,
    # and must never expose a UUID.
    assert "TEMU1234567" in exc.value.message
    assert "2026-06-01" in exc.value.message
    assert "2026-06-20" in exc.value.message
    assert str(first.id) not in exc.value.message
    # Nothing created, nothing mutated.
    assert db.query(InboundShipment).count() == 1
    assert first.attachment_id == att1


# ---- 3/4: genuine container reuse still works ------------------------------


def test_different_eta_on_received_container_creates_new(db):
    """Case 3 — container genuinely reused; ETA differs -> not a duplicate."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
    )
    _received(db, first)

    second = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 9, 15),
        attachment_id=att2,
    )
    db.commit()

    assert second.id != first.id
    assert db.query(InboundShipment).count() == 2


def test_different_shipment_date_on_received_container_creates_new(db):
    """Case 4 — container genuinely reused; sail date differs -> not a duplicate."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
    )
    _received(db, first)

    second = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 9, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att2,
    )
    db.commit()

    assert second.id != first.id
    assert db.query(InboundShipment).count() == 2


# ---- 5/6: NULL semantics ---------------------------------------------------


def test_eta_null_on_both_sides_is_a_duplicate(db):
    """Case 5 — NULL == NULL is equal, so the triple still matches."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        attachment_id=att1,
    )
    _received(db, first)

    with pytest.raises(DuplicatePackingListError):
        _create(
            db,
            p,
            shipping_container_number="TEMU1234567",
            shipment_date=date(2026, 6, 1),
            attachment_id=att2,
        )
    assert db.query(InboundShipment).count() == 1


def test_eta_null_on_payload_but_set_on_existing_creates_new(db):
    """Case 6 — NULL vs a value is NOT equal, so this is not a duplicate."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
    )
    _received(db, first)

    second = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        attachment_id=att2,
    )
    db.commit()

    assert second.id != first.id
    assert db.query(InboundShipment).count() == 2


# ---- 7: no container -> no dedup ------------------------------------------


def test_null_container_on_payload_skips_dedup_and_creates(db):
    """Case 7 — regression guard.

    Without a container the key would collapse to shipment_date alone, which
    would falsely block two different suppliers shipping on the same day.
    """
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(db, p, shipment_date=date(2026, 6, 1), attachment_id=att1)
    _received(db, first)

    second = _create(db, p, shipment_date=date(2026, 6, 1), attachment_id=att2)
    db.commit()

    assert second.id != first.id
    assert db.query(InboundShipment).count() == 2


# ---- 8/9: pre-GRN correction flow must survive -----------------------------


@pytest.mark.parametrize("open_status", ["in_transit", "partial_received"])
def test_not_yet_received_container_still_updates_in_place(db, open_status):
    """Case 8 + 9 — regression guard.

    Re-uploading a corrected packing list before GRN must keep updating the same
    row. Rejection applies only where update-in-place was already impossible.
    """
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
        lines=[(p, 5)],
    )
    first.shipment_status = open_status
    db.commit()

    second = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att2,
        lines=[(p, 9)],
    )
    db.commit()

    assert second.id == first.id
    assert getattr(second, "_already_existed", False) is True
    assert db.query(InboundShipment).count() == 1
    assert sum(l.quantity_shipped for l in second.shipment_lines) == 9


# ---- 10: container normalization ------------------------------------------


@pytest.mark.parametrize(
    "reuploaded_as",
    ["temu 1234567", "TEMU-1234567", "temu/1234567", "  TEMU1234567  "],
)
def test_container_formatting_variance_still_detected(db, reuploaded_as):
    """Case 10 — LLM extraction is not deterministic; a stray space or dash must
    not let the duplicate through."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att1,
    )
    _received(db, first)

    with pytest.raises(DuplicatePackingListError):
        _create(
            db,
            p,
            shipping_container_number=reuploaded_as,
            shipment_date=date(2026, 6, 1),
            estimated_arrival_date=date(2026, 6, 20),
            attachment_id=att2,
        )
    assert db.query(InboundShipment).count() == 1


# ---- 11: several past shipments on the same container ----------------------


def test_matches_against_any_received_shipment_on_that_container(db):
    """Case 11 — a container reused several times: the triple must be compared
    against every past shipment carrying it, not just the first row found."""
    p = _product(db, "SKU-A")
    att1, att2, att3 = _attachment(db), _attachment(db), _attachment(db)
    db.commit()

    older = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 1, 10),
        estimated_arrival_date=date(2026, 2, 1),
        attachment_id=att1,
    )
    _received(db, older)

    newer = _create(
        db,
        p,
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        estimated_arrival_date=date(2026, 6, 20),
        attachment_id=att2,
    )
    _received(db, newer)
    assert db.query(InboundShipment).count() == 2

    # Re-upload of the OLDER packing list — must still be caught.
    with pytest.raises(DuplicatePackingListError):
        _create(
            db,
            p,
            shipping_container_number="TEMU1234567",
            shipment_date=date(2026, 1, 10),
            estimated_arrival_date=date(2026, 2, 1),
            attachment_id=att3,
        )
    assert db.query(InboundShipment).count() == 2


# ---- 12/13: integration_log stamping --------------------------------------


def _integration_log(db, attachment_id: str, **overrides) -> IntegrationLog:
    log = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel="n8n",
        business_table="attachments",
        business_id=str(attachment_id),
        direction="outbound",
        endpoint="/webhook/packing-list",
        http_method="POST",
        status="sent",
        **overrides,
    )
    db.add(log)
    db.commit()
    return log


def test_integration_log_is_stamped_with_code_and_message(db):
    """Case 12 — the drawer reads the error_code/error_message COLUMNS, which
    n8n never writes. Stamp them ourselves so the user sees the real reason."""
    from app.api.v1.external.packing_lists import stamp_duplicate_integration_log

    att = _attachment(db)
    db.commit()
    log = _integration_log(db, att)

    stamp_duplicate_integration_log(db, att, "DUPLICATE_PACKING_LIST", "Container TEMU1234567 ...")

    db.refresh(log)
    assert log.error_code == "DUPLICATE_PACKING_LIST"
    assert log.error_message.startswith("Container TEMU1234567")
    # Status is n8n's to set; we must not pre-empt it.
    assert log.status == "sent"


def test_stamping_picks_the_latest_log_for_the_attachment(db):
    """Retries create several log rows — stamp the newest, which is the one the
    drawer surfaces (upload_activity.py orders by created_at desc and keeps the
    first per attachment; this must agree with it).

    created_at is set explicitly: the server default would give both rows the
    same timestamp and the assertion would be measuring clock resolution.
    """
    from app.api.v1.external.packing_lists import stamp_duplicate_integration_log

    att = _attachment(db)
    db.commit()
    old = _integration_log(db, att, created_at=datetime(2026, 6, 1, 10, 0, 0))
    new = _integration_log(db, att, created_at=datetime(2026, 6, 1, 10, 5, 0))

    stamp_duplicate_integration_log(db, att, "DUPLICATE_PACKING_LIST", "msg")

    db.refresh(old)
    db.refresh(new)
    assert new.error_code == "DUPLICATE_PACKING_LIST"
    assert old.error_code is None


def test_stamping_is_a_noop_when_no_log_row_exists(db):
    """Case 13 — a direct API call (no n8n) has no log row; rejection must still
    work rather than 500."""
    from app.api.v1.external.packing_lists import stamp_duplicate_integration_log

    att = _attachment(db)
    db.commit()

    stamp_duplicate_integration_log(db, att, "DUPLICATE_PACKING_LIST", "msg")  # must not raise
    assert db.query(IntegrationLog).count() == 0


# ---- 14: shipment_number path unchanged ------------------------------------


def test_shipment_number_match_keeps_its_own_completed_error(db):
    """Case 14 — when a shipment number IS present it still wins, and a received
    match still raises the pre-existing 'already completed' conflict, not the new
    duplicate error."""
    p = _product(db, "SKU-A")
    att1, att2 = _attachment(db), _attachment(db)
    db.commit()

    first = _create(
        db,
        p,
        shipment_number="SH-1",
        shipping_container_number="TEMU1234567",
        shipment_date=date(2026, 6, 1),
        attachment_id=att1,
    )
    _received(db, first)

    with pytest.raises(Exception) as exc:
        _create(
            db,
            p,
            shipment_number="SH-1",
            shipping_container_number="TEMU9999999",
            shipment_date=date(2026, 7, 1),
            attachment_id=att2,
        )
    assert not isinstance(exc.value, DuplicatePackingListError)
    assert db.query(InboundShipment).count() == 1


# ---- both create routes must surface 409, never 500 ------------------------


def test_both_create_routes_translate_the_error_to_409():
    """The manual UI route wraps create_shipment in a bare `except Exception ->
    handle_internal_error`, which would turn this user-fixable mistake into a
    500. Both routes must catch DuplicatePackingListError explicitly.
    """
    import inspect

    from app.api.v1.external import packing_lists as external_route
    from app.api.v1.procurement import packing_lists as internal_route

    for module in (external_route, internal_route):
        src = inspect.getsource(module.create_packing_list)
        assert "DuplicatePackingListError" in src, (
            f"{module.__name__}.create_packing_list must handle "
            "DuplicatePackingListError or it becomes a 500"
        )
        assert "HTTP_409_CONFLICT" in src
