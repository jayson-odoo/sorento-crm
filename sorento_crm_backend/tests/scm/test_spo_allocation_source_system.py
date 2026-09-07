"""AC-X53 (writers stamp) - spo-xlsx-supersede round 7, security round 6, PLAN D25c amended.

`spo_conversion_service._write_allocations` and `allocation_suggestion_service`'s accept
path (`approve`) each raise ONE `spo_allocations` row per purchase-order line - never an
Excel aggregate - and must stamp `source_system = 'crm_spo'` so the first-push supersede's
`is_xlsx_era_row` guard (AC-X52) leaves them alone regardless of `po_line_id`.
`SPOAllocationCreate.source_system` is optional so this is additive, not a breaking change
to any other caller's shape.

Postgres only (`pg_session`), marker-prefixed, every test seeds its own chain. Fixtures
reused wholesale from the two services' own test files (`tests/scm/test_spo_conversion.py`,
`tests/scm/test_allocation_suggestion.py`) per the tester brief - imported, not copied.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date

from app.models.procurement import SPOAllocation
from app.services.scm import allocation_suggestion_service as suggestion_svc
from app.services.scm import spo_conversion_service as conversion_svc
from tests._pg_fixture import pg_session
from tests.scm.test_allocation_suggestion import World as SuggestionWorld
from tests.scm.test_spo_conversion import World as ConversionWorld


def test_spo_conversion_create_stamps_source_system_crm_spo_on_every_allocation():
    """AC-X53. `spo_conversion_service.create` (which reaches `_write_allocations`) must
    stamp `source_system = 'crm_spo'` on every SPOAllocation row it writes.

    RED today: `_write_allocations` never passes `source_system` to `SPOAllocationCreate`
    at all - every row it writes has NULL, which the D25c predicate cannot distinguish
    from a genuine Excel aggregate (the exact AC-X52 hazard: superseding a PO-linked row
    would sever the PO -> SPO -> GRN chain silently).
    """
    with pg_session() as db:
        w = ConversionWorld(db)
        warehouse = w.warehouse("SELLABLE")
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])

        # A confirm line writes an allocation only when it names a location
        # to land in (B4, review round 1 - the link a confirm writes hangs
        # off an allocation, so a bare qty/include pair with no
        # `location_splits` writes an SPO line but no allocation at all).
        conversion_svc.create(
            db, str(shipment.id),
            [{
                "shipment_line_id": str(lines[0].id), "qty": 40, "include": True,
                "location_splits": [{"warehouse_id": str(warehouse.id), "qty": 40}],
            }],
            actor="tester",
        )

        allocations = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id == shipment.id)
            .all()
        )
        assert allocations, "the conversion must have written at least one allocation"
        for allocation in allocations:
            assert allocation.source_system == "crm_spo", (
                "every spo_conversion_service-written allocation must be stamped "
                f"crm_spo - got {allocation.source_system!r} on {allocation.id}"
            )


def test_allocation_suggestion_approve_stamps_source_system_crm_spo():
    """AC-X53, `allocation_suggestion_service`'s accept path. `approve` must stamp the
    same `crm_spo` marker on the SPOAllocation row it writes - the IDENTICAL write
    `spo_conversion_service._write_allocations` uses (`SPOAllocationService.
    create_allocation`), so the two writers can never disagree about what stamps a row
    as "one line, one PO line, never an aggregate".

    RED today: `approve` builds `SPOAllocationCreate` with no `source_system` at all.
    """
    with pg_session() as db:
        w = SuggestionWorld(db)
        w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        suggestion = suggestion_svc.suggest(db, str(shipment.id))["lines"][0]

        suggestion_svc.approve(db, str(shipment.id), [
            {
                "shipment_line_id": suggestion["shipment_line_id"],
                "splits": [{
                    "po_line_id": suggestion["suggestion"]["po_line_id"],
                    "warehouse_id": suggestion["suggestion"]["warehouse_id"],
                    "qty": 10,
                }],
            }
        ])

        allocation = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id == shipment.id)
            .one()
        )
        assert allocation.source_system == "crm_spo", (
            "allocation_suggestion_service.approve must stamp crm_spo - got "
            f"{allocation.source_system!r}"
        )


# ============================================================================ #
# Round 8 (PLAN D25c, external ingest surfaces / `CRM_RAISED_SOURCE_SYSTEMS`)
# ============================================================================ #
# AC-X58 (`upsert_allocation` corrects a crm_spo row's quantity in place)


def test_upsert_allocation_matches_and_corrects_a_crm_spo_row_leaving_source_system_alone():
    """AC-X58. `upsert_allocation` (keyed on spo_number/product_id/warehouse_id) must
    MATCH an existing `crm_spo` row - correcting its `allocated_quantity` in place,
    the SAME row id, `source_system` left exactly as `crm_spo` - rather than creating a
    second row for the same triple.

    Given the current `upsert_allocation` code already names `CRM_SPO_SOURCE_SYSTEM`
    in its match filter's `or_(...)` (security round 7), this is expected to already
    be green; written to pin the contract regardless, per the round 8 brief.
    """
    from app.schemas.procurement import SPOAllocationCreate
    from app.services.procurement_service import SPOAllocationService

    with pg_session() as db:
        w = ConversionWorld(db)
        warehouse = w.warehouse("SELLABLE")
        product = w.product("A")
        supplier = w.supplier()
        shipment, _lines = w.shipment([("A", 10, supplier)])

        service = SPOAllocationService(db)
        spo_number = f"ZZSPOC-UPSERT-{_uuid.uuid4().hex[:8]}"

        existing = SPOAllocation(
            id=str(_uuid.uuid4()), spo_number=spo_number, product_id=product.id,
            warehouse_id=warehouse.id, inbound_shipment_id=shipment.id,
            allocated_quantity=10, quantity_received=0, line_status="open",
            receipt_status="pending", source_system="crm_spo",
        )
        db.add(existing)
        db.flush()
        db.commit()

        action, allocation = service.upsert_allocation(
            SPOAllocationCreate(
                spo_number=spo_number,
                product_id=str(product.id),
                warehouse_id=str(warehouse.id),
                inbound_shipment_id=str(shipment.id),
                allocated_quantity=12,
            ),
            created_by="tester",
            forward_match=False,
        )

        assert action == "updated", action
        assert str(allocation.id) == str(existing.id), (
            "upsert must MATCH the existing crm_spo row, never create a second one"
        )
        assert int(allocation.allocated_quantity) == 12, allocation.allocated_quantity
        assert allocation.source_system == "crm_spo", (
            f"source_system must stay crm_spo, untouched - got {allocation.source_system!r}"
        )

        rows = (
            db.query(SPOAllocation)
            .filter(
                SPOAllocation.spo_number == spo_number,
                SPOAllocation.product_id == product.id,
                SPOAllocation.warehouse_id == warehouse.id,
            )
            .all()
        )
        assert len(rows) == 1, (
            f"no second row must exist for the same triple - got {rows}"
        )


# ============================================================================ #
# AC-X60 (procurement create route cannot set source_system)
# ============================================================================ #


def test_procurement_create_route_ignores_a_client_supplied_source_system(scm_app):
    """AC-X60. `POST /api/v1/procurement/spo-allocations` (an authenticated
    procurement user's own create action) must never let the CALLER set
    `source_system` - only the two in-process SCM writers
    (`spo_conversion_service._write_allocations`,
    `allocation_suggestion_service.approve`) may stamp it. A request body
    naming `source_system: 'autocount'` must create the row with
    `source_system NULL`.

    Checked statically: `SPOAllocationCreate`/`SPOAllocationBase` set no
    `model_config` of their own, so they inherit pydantic's default
    `extra="ignore"` (unlike `InboundShipmentUpdate`, which deliberately
    opts into `extra="forbid"` a few classes up in the same file) - so
    EITHER a fix that strips `source_system` before the write OR one that
    removes the field from the schema entirely both land on the same
    answer: 201, not 422.

    RED today: the route parses the body straight into `SPOAllocationCreate`
    (the SAME schema the two SCM writers use, which now carries an optional
    `source_system` field) and hands it UNCHANGED to `create_allocation` -
    nothing strips or refuses a client-supplied value, so the row is
    written with `source_system = 'autocount'` exactly as the caller
    asked. Any authenticated procurement user could otherwise forge the
    marker the first-push supersede treats as "never touch this row".
    """
    from datetime import date as _date

    from fastapi.testclient import TestClient
    from sqlalchemy import text as _text

    from app.models.procurement import InboundShipment
    from tests.scm.conftest import as_user, seed_user

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "purchasing")
    as_user(app, gcu, gcuak, uid)

    w = ConversionWorld(db)
    warehouse = w.warehouse("SELLABLE")
    product = w.product("A")
    shipment = InboundShipment(
        id=str(_uuid.uuid4()), shipment_number=f"ZZSPOC-SH60-{_uuid.uuid4().hex[:6]}",
        shipment_date=_date(2026, 3, 1), shipment_status="pending",
    )
    db.add(shipment)
    db.flush()
    db.commit()

    spo_number = f"ZZSPOC-X60-{_uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/procurement/spo-allocations/",
            json={
                "spo_number": spo_number,
                "product_id": str(product.id),
                "warehouse_id": str(warehouse.id),
                "inbound_shipment_id": str(shipment.id),
                "allocated_quantity": 10,
                "source_system": "autocount",
            },
        )

    assert response.status_code == 201, response.text
    allocation_id = response.json()["id"]

    row = db.execute(
        _text("SELECT source_system FROM spo_allocations WHERE id = :id"),
        {"id": allocation_id},
    ).mappings().first()
    assert row["source_system"] is None, (
        "a client-supplied source_system must never reach the row - the "
        f"create request cannot set it - got {row}"
    )
