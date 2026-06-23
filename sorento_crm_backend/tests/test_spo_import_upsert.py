"""SPOAllocationService.upsert_allocation — SPO import upserts instead of skipping.

Re-importing a corrected SPO file overwrites the existing allocation's
allocated_quantity (file is source of truth) instead of skipping the row. A
guard refuses to drop allocated_quantity below what has already been received.

Covers PLAN-spo-import-upsert / UAC AC-SPO-1..7.
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

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
from app.schemas.procurement import SPOAllocationCreate
from app.services.procurement_service import (
    SPOAllocationService,
    AllocationReceivedGuardError,
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
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _product(db, code: str = "SKU-A") -> str:
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


def _shipment(db, container: str = "CONT-1") -> str:
    sid = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=sid,
            shipment_number=f"SH-{container}",
            shipping_container_number=container,
            shipment_date=date(2026, 1, 1),
            shipment_status="pending",
        )
    )
    db.flush()
    return sid


def _warehouse_id() -> str:
    # No FK enforcement on sqlite by default; a bare UUID is enough for the key.
    return str(uuid.uuid4())


def _payload(spo, product_id, warehouse_id, shipment_id, qty) -> SPOAllocationCreate:
    return SPOAllocationCreate(
        spo_number=spo,
        inbound_shipment_id=shipment_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        allocated_quantity=qty,
        receipt_status="pending",
        quantity_received=0,
        quantity_rejected=0,
    )


@pytest.fixture
def stub_refresh():
    """The shipment-line refresh joins tables not worth wiring on sqlite; stub it
    and assert it was invoked (AC-SPO-7)."""
    with patch(
        "app.services.procurement_service.InboundShipmentService.refresh_shipment_line_statuses"
    ) as m:
        yield m


def _seed_existing(db, **overrides) -> SPOAllocation:
    spo = overrides.pop("spo_number", "SPO-A")
    product_id = overrides.pop("product_id", None) or _product(db)
    warehouse_id = overrides.pop("warehouse_id", None) or _warehouse_id()
    shipment_id = overrides.pop("inbound_shipment_id", None) or _shipment(db)
    alloc = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=spo,
        inbound_shipment_id=shipment_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        allocated_quantity=overrides.pop("allocated_quantity", 10),
        receipt_status=overrides.pop("receipt_status", "pending"),
        quantity_received=overrides.pop("quantity_received", 0),
        quantity_rejected=overrides.pop("quantity_rejected", 0),
        created_by=overrides.pop("created_by", "seed-user"),
    )
    db.add(alloc)
    db.commit()
    db.refresh(alloc)
    return alloc


# AC-SPO-1
def test_new_allocation_created(db, stub_refresh):
    product_id = _product(db)
    warehouse_id = _warehouse_id()
    shipment_id = _shipment(db)
    db.commit()

    action, alloc = SPOAllocationService(db).upsert_allocation(
        _payload("SPO-A", product_id, warehouse_id, shipment_id, 12), "importer"
    )

    assert action == "created"
    assert alloc.allocated_quantity == 12
    assert alloc.created_by == "importer"
    assert db.query(SPOAllocation).count() == 1
    stub_refresh.assert_called_once_with(shipment_id)


# AC-SPO-2
def test_existing_higher_qty_updated_others_untouched(db, stub_refresh):
    existing = _seed_existing(
        db, allocated_quantity=10, quantity_received=0, receipt_status="pending",
        created_by="original",
    )
    stub_refresh.reset_mock()

    action, alloc = SPOAllocationService(db).upsert_allocation(
        _payload(
            existing.spo_number, existing.product_id, existing.warehouse_id,
            existing.inbound_shipment_id, 15,
        ),
        "importer",
    )

    assert action == "updated"
    assert alloc.id == existing.id
    assert alloc.allocated_quantity == 15
    # Only allocated_quantity changes; the rest is left alone.
    assert alloc.quantity_received == 0
    assert alloc.receipt_status == "pending"
    assert alloc.created_by == "original"
    assert alloc.updated_at is not None
    assert db.query(SPOAllocation).count() == 1


# AC-SPO-3
def test_existing_lower_but_at_or_above_received_updated(db, stub_refresh):
    existing = _seed_existing(db, allocated_quantity=10, quantity_received=3)
    stub_refresh.reset_mock()

    action, alloc = SPOAllocationService(db).upsert_allocation(
        _payload(
            existing.spo_number, existing.product_id, existing.warehouse_id,
            existing.inbound_shipment_id, 5,
        ),
        "importer",
    )

    assert action == "updated"
    assert alloc.allocated_quantity == 5
    assert alloc.quantity_received == 3


# AC-SPO-5
def test_identical_qty_unchanged_no_write(db, stub_refresh):
    existing = _seed_existing(db, allocated_quantity=10)
    stub_refresh.reset_mock()

    action, alloc = SPOAllocationService(db).upsert_allocation(
        _payload(
            existing.spo_number, existing.product_id, existing.warehouse_id,
            existing.inbound_shipment_id, 10,
        ),
        "importer",
    )

    assert action == "unchanged"
    assert alloc.allocated_quantity == 10
    assert alloc.updated_at is None  # no write happened
    stub_refresh.assert_not_called()


# AC-SPO-4
def test_guard_new_qty_below_received_raises_and_no_change(db, stub_refresh):
    existing = _seed_existing(db, allocated_quantity=10, quantity_received=8)
    stub_refresh.reset_mock()

    with pytest.raises(AllocationReceivedGuardError) as exc:
        SPOAllocationService(db).upsert_allocation(
            _payload(
                existing.spo_number, existing.product_id, existing.warehouse_id,
                existing.inbound_shipment_id, 5,
            ),
            "importer",
        )

    msg = str(exc.value)
    assert existing.spo_number in msg
    assert existing.product_id in msg
    assert existing.warehouse_id in msg
    assert "5" in msg
    assert "8" in msg

    db.expire_all()
    refreshed = db.query(SPOAllocation).filter(SPOAllocation.id == existing.id).first()
    assert refreshed.allocated_quantity == 10  # untouched
    stub_refresh.assert_not_called()


# AC-SPO-6 — mixed file drives process_spo_import counter aggregation
def test_mixed_file_counters(db, stub_refresh):
    """One new + one higher-qty update + one identical + one guarded row, in a
    single SPO file → created:1, updated:1, unchanged excluded from updated, the
    guarded row in errors[] + skipped_rows_count:1, no 'Skipped duplicate'."""
    import types
    from io import BytesIO
    import openpyxl
    from app.tasks import import_tasks as it

    spo = "SPO-MIX"
    wh = _warehouse_id()
    ship = _shipment(db, "CONT-MIX")
    p_upd = _product(db, "P-UPD")
    p_unc = _product(db, "P-UNC")
    p_grd = _product(db, "P-GRD")
    p_new = _product(db, "P-NEW")
    # Seed the three existing allocations.
    _seed_existing(db, spo_number=spo, product_id=p_upd, warehouse_id=wh,
                   inbound_shipment_id=ship, allocated_quantity=10, quantity_received=0)
    _seed_existing(db, spo_number=spo, product_id=p_unc, warehouse_id=wh,
                   inbound_shipment_id=ship, allocated_quantity=10, quantity_received=0)
    _seed_existing(db, spo_number=spo, product_id=p_grd, warehouse_id=wh,
                   inbound_shipment_id=ship, allocated_quantity=10, quantity_received=8)
    db.commit()

    # Build a real 4-row xlsx: each row a distinct product, one warehouse, one container.
    wbk = openpyxl.Workbook()
    sh = wbk.active
    sh.append(["Item Code", "Location", "Qty", "Loading Date"])
    sh.append(["P-UPD", "WH1", 15, "2026-01-01 CONT-MIX"])  # 10 -> 15 update
    sh.append(["P-UNC", "WH1", 10, "2026-01-01 CONT-MIX"])  # 10 -> 10 unchanged
    sh.append(["P-GRD", "WH1", 5, "2026-01-01 CONT-MIX"])   # 5 < received 8 -> guarded
    sh.append(["P-NEW", "WH1", 7, "2026-01-01 CONT-MIX"])   # new -> created
    buf = BytesIO(); wbk.save(buf); file_bytes = buf.getvalue()

    captured = {}

    class _FakeJob:
        job_id = "job-mix"

    class _FakeJobService:
        def __init__(self, _db): pass
        def get_job_by_db_id(self, _i): return _FakeJob()
        def get_job(self, _i): return _FakeJob()
        def start_job(self, _i): pass
        def update_job_progress(self, *a, **k): pass
        def fail_job(self, _i, msg): captured["failed"] = msg
        def complete_job(self, **kw): captured["result"] = kw["result"]

    prod_objs = {
        "P-UPD": types.SimpleNamespace(id=p_upd),
        "P-UNC": types.SimpleNamespace(id=p_unc),
        "P-GRD": types.SimpleNamespace(id=p_grd),
        "P-NEW": types.SimpleNamespace(id=p_new),
    }
    wh_obj = types.SimpleNamespace(id=wh)
    ship_obj = types.SimpleNamespace(id=ship)

    with patch.object(it, "SessionLocal", lambda: db), \
         patch.object(it, "JobService", _FakeJobService), \
         patch.object(it, "get_products_by_code_exact", lambda _db, codes: {c: prod_objs[c] for c in codes if c in prod_objs}), \
         patch.object(it, "get_warehouses_by_code_or_name", lambda _db, locs: {"WH1": wh_obj}), \
         patch.object(it, "get_inbound_shipment_by_container_number", lambda _db, _c: ship_obj), \
         patch("app.api.v1.external.utils.normalize_code", lambda x: x), \
         patch.object(db, "close", lambda: None):
        it.process_spo_import("dbjob-mix", file_bytes, f"{spo}.xlsx", "importer")

    res = captured["result"]
    assert res["allocations_created"] == 1, res
    assert res["allocations_updated"] == 1, res
    assert res["allocations_unchanged"] == 1, res
    assert res["skipped_rows_count"] == 1, res
    # Guarded row surfaced with explicit message; no generic "Skipped duplicate".
    joined = " ".join(res["errors"])
    assert "already received" in joined and "8" in joined, res["errors"]
    assert "Skipped duplicate" not in joined
    # DB end-state: update applied, unchanged left at 10, guarded left at 10, new created.
    db.expire_all()
    assert db.query(SPOAllocation).filter_by(product_id=p_upd).first().allocated_quantity == 15
    assert db.query(SPOAllocation).filter_by(product_id=p_unc).first().allocated_quantity == 10
    assert db.query(SPOAllocation).filter_by(product_id=p_grd).first().allocated_quantity == 10
    assert db.query(SPOAllocation).filter_by(product_id=p_new).first().allocated_quantity == 7


# AC-SPO-7 (explicit refresh assertion on update)
def test_shipment_line_status_refreshed_after_update(db, stub_refresh):
    existing = _seed_existing(db, allocated_quantity=10, quantity_received=0)
    stub_refresh.reset_mock()

    SPOAllocationService(db).upsert_allocation(
        _payload(
            existing.spo_number, existing.product_id, existing.warehouse_id,
            existing.inbound_shipment_id, 20,
        ),
        "importer",
    )

    stub_refresh.assert_called_once_with(existing.inbound_shipment_id)
