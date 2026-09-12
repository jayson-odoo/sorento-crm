"""AC-X56, AC-X57 - spo-xlsx-supersede round 8 (PLAN D25c, `CRM_RAISED_SOURCE_SYSTEMS`).

`POST /api/v1/external/grn` and `POST /api/v1/external/spo-allocations` must treat a
`crm_spo`-stamped `spo_allocations` row (`spo_conversion_service._write_allocations` /
`allocation_suggestion_service.approve`, AC-X53) exactly like a NULL-source row: the
external GRN's `(spo_number, product_id, warehouse_id)` resolution must accept it, and
the n8n bulk-create's duplicate guard must refuse a second row for the same triple.
Both routes today filter `SPOAllocation.source_system.is_(None)` only, excluding
`crm_spo`.

Fixture reused wholesale from `tests/test_external_company_anchor_scope.py` (`env`, `GRN`)
per the tester brief - imported, not copied. That file already drives both external
routes' TestClient/db/company plumbing; a new file here avoids editing an owned one.
"""
from __future__ import annotations

import uuid

from app.models.procurement import InboundShipment, PickingHeader, PickingLine, SPOAllocation

from tests.test_external_company_anchor_scope import GRN, env  # noqa: F401 - pytest fixture

__all__ = ["env"]

SPO_ALLOCATIONS = "/api/v1/external/spo-allocations/"
MARKER = "ZZTX56"


def test_external_grn_resolves_a_crm_spo_allocation_by_the_triple(env):
    """AC-X56. A GRN naming (spo_number, product_code, warehouse) that resolves ONLY
    to a `crm_spo`-stamped allocation (no NULL-source row exists for this triple) must
    be accepted, not refused as "no SPO allocation found".

    `create_grn` never links `spo_allocation_id` at create time regardless of
    `source_system` ("a GRN links on approval, not on create" - `app/services/
    procurement_service.py::create_grn`, `line_dict.pop("spo_allocation_id", None)`),
    so the observable proof the triple resolved is (a) the request is NOT refused
    with the route's own 400 "No SPO allocation found for spo_number + product +
    warehouse" and (b) the picking line's `destination_warehouse_id` - set ONLY when
    the route's own lookup found an allocation - carries the crm_spo row's warehouse.

    RED today: the triple-lookup query filters `SPOAllocation.source_system.is_(None)`
    only. With no NULL-source row seeded for this triple (only the `crm_spo` one), the
    lookup finds nothing and `get_alloc_for_line` raises 400 - the exact production
    gap: a legitimate CRM-raised allocation refuses the GRN meant to receive against it.
    """
    code = f"{MARKER}-P-{uuid.uuid4().hex[:6]}"
    product = env.product(code, env.company_a)
    warehouse = env.warehouse(f"{MARKER}WH{uuid.uuid4().hex[:6]}", env.company_a)
    spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

    allocation = SPOAllocation(
        id=str(uuid.uuid4()), company_id=env.company_a, spo_number=spo_number,
        spo_line_number=1, product_id=product.id, warehouse_id=warehouse.id,
        allocated_quantity=10, quantity_received=0, line_status="open",
        receipt_status="pending", source_system="crm_spo",
    )
    env.db.add(allocation)
    env.db.flush()
    env.db.commit()

    picking_number = f"{MARKER}-{uuid.uuid4().hex[:6]}"
    response = env.client.post(
        GRN,
        json={
            "goods_receive_notes": {
                "picking_number": picking_number,
                "picking_date": "2026-03-10",
            },
            "grn_lines": [
                {
                    "product_code": code,
                    "quantity": 5,
                    "location": warehouse.warehouse_code,
                    "spo_allocation": spo_number,
                }
            ],
        },
    )
    assert response.status_code in (200, 201), (
        "a crm_spo allocation must resolve the triple, not refuse the GRN as "
        f"'no SPO allocation found' - got {response.status_code}: {response.text}"
    )

    header = (
        env.db.query(PickingHeader)
        .filter(PickingHeader.picking_number == picking_number)
        .one()
    )
    line = env.db.query(PickingLine).filter(PickingLine.picking_header_id == header.id).one()
    assert line.spo_number_raw == spo_number, line.spo_number_raw
    assert line.destination_warehouse_id is not None and str(
        line.destination_warehouse_id
    ) == str(warehouse.id), (
        "destination_warehouse_id is set ONLY when the route's own triple lookup "
        f"found an allocation - the crm_spo row must have resolved it - got {line.destination_warehouse_id}"
    )


def test_n8n_bulk_create_refuses_a_duplicate_triple_against_a_crm_spo_row(env):
    """AC-X57. A bulk-create item naming the SAME (spo_number, product, warehouse)
    triple as an existing `crm_spo` row must be refused as a duplicate, the same way
    it already is for a NULL-source row.

    RED today: the duplicate-check query also filters `source_system.is_(None)` only
    - a `crm_spo` row is invisible to it, so the item is NOT refused: a second
    `spo_allocations` row is created for the same triple instead.
    """
    code = f"{MARKER}-P-{uuid.uuid4().hex[:6]}"
    product = env.product(code, env.company_a)
    warehouse = env.warehouse(f"{MARKER}WH{uuid.uuid4().hex[:6]}", env.company_a)
    spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

    existing = SPOAllocation(
        id=str(uuid.uuid4()), company_id=env.company_a, spo_number=spo_number,
        spo_line_number=1, product_id=product.id, warehouse_id=warehouse.id,
        allocated_quantity=10, quantity_received=0, line_status="open",
        receipt_status="pending", source_system="crm_spo",
    )
    env.db.add(existing)
    env.db.flush()

    from datetime import date

    shipment = InboundShipment(
        id=str(uuid.uuid4()), shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:6]}",
        shipment_date=date(2026, 3, 1), shipment_status="pending",
    )
    env.db.add(shipment)
    env.db.flush()
    env.db.commit()

    response = env.client.post(
        SPO_ALLOCATIONS,
        json={
            "spo_allocations": [
                {
                    "spo_number": spo_number,
                    "product_code": code,
                    "location": warehouse.warehouse_code,
                    "quantity": 7,
                    "inbound_shipment_id": str(shipment.id),
                }
            ]
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body.get("data") == [], (
        "a duplicate triple against a crm_spo row must create NOTHING", body
    )
    reasons = [ve.get("reason") for ve in (body.get("validation_errors") or [])]
    assert any("already exists" in (reason or "") for reason in reasons), (
        f"expected a duplicate-combination refusal - got {body}"
    )

    rows = (
        env.db.query(SPOAllocation)
        .filter(
            SPOAllocation.spo_number == spo_number,
            SPOAllocation.product_id == product.id,
            SPOAllocation.warehouse_id == warehouse.id,
        )
        .all()
    )
    assert len(rows) == 1, (
        "the crm_spo row must stay the ONLY row for this triple - no second row "
        f"created - got {rows}"
    )
