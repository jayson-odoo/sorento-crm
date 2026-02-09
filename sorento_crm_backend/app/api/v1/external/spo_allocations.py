"""External API for SPO allocations."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import SPOAllocationRequest
from app.models.procurement import SPOAllocation, InboundShipment, InboundShipmentLine
from app.models.inventory import Warehouse
from app.api.v1.external.utils import (
    get_products_by_code,
    get_warehouses_by_code_or_name,
    get_inbound_shipment_by_container_number,
    get_shipment_line_by_product,
    normalize_code,
)

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_spo_allocations(
    payload: SPOAllocationRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    if not payload.spo_allocations:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No allocations provided")

    # Per-item validation: require (inbound_shipment_id or shipping_container_number), (warehouse_id or location), (allocated_quantity or quantity)
    for i, item in enumerate(payload.spo_allocations):
        if not item.inbound_shipment_id and not (item.shipping_container_number or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item {i + 1}: provide inbound_shipment_id or shipping_container_number",
            )
        if not item.warehouse_id and not (item.location or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item {i + 1}: provide warehouse_id or location (warehouse code/name)",
            )
        qty = item.quantity if item.quantity is not None else item.allocated_quantity
        if qty is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item {i + 1}: provide allocated_quantity or quantity",
            )

    # Resolve inbound_shipment_id from shipping_container_number where provided
    container_numbers = {
        (item.shipping_container_number or "").strip()
        for item in payload.spo_allocations
        if (item.shipping_container_number or "").strip() and not item.inbound_shipment_id
    }
    shipment_by_container = {}
    for cn in container_numbers:
        shipment = get_inbound_shipment_by_container_number(db, cn)
        if not shipment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Inbound shipment not found for shipping_container_number", "shipping_container_number": cn},
            )
        shipment_by_container[normalize_code(cn)] = shipment

    # Resolve warehouse_id from location where provided
    locations = {(item.location or "").strip() for item in payload.spo_allocations if (item.location or "").strip() and not item.warehouse_id}
    warehouses_by_location = get_warehouses_by_code_or_name(db, locations) if locations else {}
    for loc in locations:
        if normalize_code(loc) not in warehouses_by_location:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Warehouse not found for location", "location": loc},
            )

    # Items that have inbound_shipment_id: validate those IDs
    shipment_ids = {item.inbound_shipment_id for item in payload.spo_allocations if item.inbound_shipment_id}
    warehouse_ids = set()
    for item in payload.spo_allocations:
        if item.warehouse_id:
            warehouse_ids.add(item.warehouse_id)
        elif (item.location or "").strip():
            w = warehouses_by_location.get(normalize_code((item.location or "").strip()))
            if w:
                warehouse_ids.add(w.id)

    if shipment_ids:
        valid_shipments = {s.id for s in db.query(InboundShipment).filter(InboundShipment.id.in_(shipment_ids)).all()}
        missing = shipment_ids - valid_shipments
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid inbound_shipment_id", "ids": list(missing)},
            )
    if warehouse_ids:
        valid_warehouses = {w.id for w in db.query(Warehouse).filter(Warehouse.id.in_(warehouse_ids)).all()}
        missing = warehouse_ids - valid_warehouses
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid warehouse_id", "ids": list(missing)},
            )

    # Validate shipment line IDs when provided explicitly
    line_ids = {item.inbound_shipment_lines_id for item in payload.spo_allocations if item.inbound_shipment_lines_id}
    if line_ids:
        valid_lines = {l.id for l in db.query(InboundShipmentLine).filter(InboundShipmentLine.id.in_(line_ids)).all()}
        missing = line_ids - valid_lines
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid inbound_shipment_lines_id", "ids": list(missing)},
            )

    # Validate product codes
    product_codes = [item.product_code for item in payload.spo_allocations]
    products_map = get_products_by_code(db, product_codes)
    missing_codes = [c for c in product_codes if normalize_code(c) not in products_map]
    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Missing product codes", "product_codes": missing_codes},
        )

    # Check for existing SPO number + line number combinations
    spo_pairs = [
        (item.spo_number, item.spo_line_number)
        for item in payload.spo_allocations
        if item.spo_number is not None and item.spo_line_number is not None
    ]
    if spo_pairs:
        existing = db.query(SPOAllocation).filter(
            or_(*[
                and_(SPOAllocation.spo_number == sn, SPOAllocation.spo_line_number == ln)
                for sn, ln in spo_pairs
            ])
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SPO number and line number combination already exists.",
            )

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    code_by_product_id = {}
    allocations = []
    for item in payload.spo_allocations:
        product = products_map[normalize_code(item.product_code)]
        code_by_product_id[product.id] = item.product_code

        # Resolve inbound_shipment_id
        if item.inbound_shipment_id:
            inbound_shipment_id = item.inbound_shipment_id
        else:
            cn = (item.shipping_container_number or "").strip()
            inbound_shipment_id = shipment_by_container[normalize_code(cn)].id

        # Resolve warehouse_id
        if item.warehouse_id:
            warehouse_id = item.warehouse_id
        else:
            loc = (item.location or "").strip()
            warehouse_id = warehouses_by_location[normalize_code(loc)].id

        # Resolve inbound_shipment_lines_id: optional link to shipment line for this product
        line_id = item.inbound_shipment_lines_id
        if not line_id:
            line = get_shipment_line_by_product(db, inbound_shipment_id, product.id)
            if line:
                line_id = line.id

        qty = item.quantity if item.quantity is not None else item.allocated_quantity

        allocations.append(
            SPOAllocation(
                spo_number=item.spo_number,
                spo_line_number=item.spo_line_number,
                inbound_shipment_lines_id=line_id,
                inbound_shipment_id=inbound_shipment_id,
                warehouse_id=warehouse_id,
                storage_zone_id=item.storage_zone_id,
                allocated_quantity=qty,
                uom_id=item.uom_id,
                receipt_status=item.receipt_status or "pending",
                quantity_received=item.quantity_received or 0,
                quantity_rejected=item.quantity_rejected or 0,
                allocation_notes=item.allocation_notes,
                product_id=product.id,
                created_by=created_by,
            )
        )

    db.add_all(allocations)
    db.commit()
    for allocation in allocations:
        db.refresh(allocation)

    return {
        "data": [
            {
                "id": allocation.id,
                "spo_number": allocation.spo_number,
                "spo_line_number": allocation.spo_line_number,
                "product_id": allocation.product_id,
                "product_code": code_by_product_id.get(allocation.product_id),
            }
            for allocation in allocations
        ]
    }
