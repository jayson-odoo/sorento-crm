"""External API for SPO allocations."""
from collections import defaultdict
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import SPOAllocationRequest
from app.models.procurement import SPOAllocation, InboundShipment, InboundShipmentLine
from app.services.procurement_service import InboundShipmentService
from app.models.inventory import Warehouse
from app.api.v1.external.utils import (
    get_products_by_code,
    get_warehouses_by_code_or_name,
    get_inbound_shipment_by_container_number,
    normalize_code,
)

router = APIRouter()


@dataclass
class _ValidationError:
    item_index: int
    spo_number: str | None
    product_code: str
    reason: str


def _group_key(item, products_map, warehouses_by_location):
    """Resolve (spo_number, product_id, warehouse_id) for an item. Returns None if missing required fields."""
    spo_number = (item.spo_number or "").strip() or None
    if not spo_number:
        return None
    product = products_map.get(normalize_code(item.product_code))
    if not product:
        return None
    if item.warehouse_id:
        warehouse_id = item.warehouse_id
    elif (item.location or "").strip():
        w = warehouses_by_location.get(normalize_code((item.location or "").strip()))
        warehouse_id = w.id if w else None
    else:
        warehouse_id = None
    if not warehouse_id:
        return None
    return (spo_number, product.id, warehouse_id)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_spo_allocations(
    payload: SPOAllocationRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    if not payload.spo_allocations:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No allocations provided")

    validation_errors: list[_ValidationError] = []

    # Resolve container numbers (collect errors per container)
    container_numbers = {
        (item.shipping_container_number or "").strip()
        for item in payload.spo_allocations
        if (item.shipping_container_number or "").strip() and not item.inbound_shipment_id
    }
    shipment_by_container = {}
    for cn in container_numbers:
        shipment = get_inbound_shipment_by_container_number(db, cn)
        if not shipment:
            for i, item in enumerate(payload.spo_allocations):
                if (item.shipping_container_number or "").strip() == cn and not item.inbound_shipment_id:
                    validation_errors.append(
                        _ValidationError(
                            item_index=i + 1,
                            spo_number=(item.spo_number or "").strip() or None,
                            product_code=item.product_code,
                            reason="Inbound shipment not found for shipping_container_number",
                        )
                    )
        else:
            shipment_by_container[normalize_code(cn)] = shipment

    # Resolve warehouses from location
    locations = {
        (item.location or "").strip()
        for item in payload.spo_allocations
        if (item.location or "").strip() and not item.warehouse_id
    }
    warehouses_by_location = get_warehouses_by_code_or_name(db, locations) if locations else {}
    for loc in locations:
        if loc and normalize_code(loc) not in warehouses_by_location:
            for i, item in enumerate(payload.spo_allocations):
                if (item.location or "").strip() == loc and not item.warehouse_id:
                    validation_errors.append(
                        _ValidationError(
                            item_index=i + 1,
                            spo_number=(item.spo_number or "").strip() or None,
                            product_code=item.product_code,
                            reason="Warehouse not found for location",
                        )
                    )
    # Products map
    product_codes = [item.product_code for item in payload.spo_allocations]
    products_map = get_products_by_code(db, product_codes)
    missing_product_codes = {normalize_code(c) for c in product_codes if normalize_code(c) not in products_map}

    # Valid shipment IDs and warehouse IDs (for items that provide them directly)
    shipment_ids = {item.inbound_shipment_id for item in payload.spo_allocations if item.inbound_shipment_id}
    valid_shipments = set()
    if shipment_ids:
        valid_shipments = {s.id for s in db.query(InboundShipment).filter(InboundShipment.id.in_(shipment_ids)).all()}
    warehouse_ids = set()
    for item in payload.spo_allocations:
        if item.warehouse_id:
            warehouse_ids.add(item.warehouse_id)
        elif (item.location or "").strip():
            w = warehouses_by_location.get(normalize_code((item.location or "").strip()))
            if w:
                warehouse_ids.add(w.id)
    valid_warehouses = set()
    if warehouse_ids:
        valid_warehouses = {w.id for w in db.query(Warehouse).filter(Warehouse.id.in_(warehouse_ids)).all()}

    # Per-item validation and mark items to skip
    skip_indices = {ve.item_index for ve in validation_errors}
    for i, item in enumerate(payload.spo_allocations):
        idx = i + 1
        if idx in skip_indices:
            continue
        if not (item.spo_number or "").strip():
            validation_errors.append(_ValidationError(idx, None, item.product_code, "spo_number is required"))
            skip_indices.add(idx)
            continue
        if not item.inbound_shipment_id and not (item.shipping_container_number or "").strip():
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "provide inbound_shipment_id or shipping_container_number")
            )
            skip_indices.add(idx)
            continue
        if not item.warehouse_id and not (item.location or "").strip():
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "provide warehouse_id or location")
            )
            skip_indices.add(idx)
            continue
        qty = item.quantity if item.quantity is not None else item.allocated_quantity
        if qty is None:
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "provide allocated_quantity or quantity")
            )
            skip_indices.add(idx)
            continue
        if normalize_code(item.product_code) in missing_product_codes:
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "Product code not found")
            )
            skip_indices.add(idx)
            continue
        if item.inbound_shipment_id and item.inbound_shipment_id not in valid_shipments:
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "Invalid inbound_shipment_id")
            )
            skip_indices.add(idx)
            continue
        wh_id = None
        if item.warehouse_id:
            wh_id = item.warehouse_id if item.warehouse_id in valid_warehouses else None
        elif (item.location or "").strip():
            w = warehouses_by_location.get(normalize_code((item.location or "").strip()))
            wh_id = w.id if w else None
        if item.warehouse_id and wh_id is None:
            validation_errors.append(
                _ValidationError(idx, (item.spo_number or "").strip(), item.product_code, "Invalid warehouse_id")
            )
            skip_indices.add(idx)
            continue
        if (item.location or "").strip() and wh_id is None and not item.warehouse_id:
            # Already added in location loop
            skip_indices.add(idx)
            continue

    # Group valid items by (spo_number, product_id, warehouse_id)
    valid_items = [item for i, item in enumerate(payload.spo_allocations) if (i + 1) not in skip_indices]
    groups = defaultdict(list)
    for item in valid_items:
        key = _group_key(item, products_map, warehouses_by_location)
        if key is None:
            continue
        groups[key].append(item)

    # Check for existing (spo_number, product_id, warehouse_id); skip those groups
    groups_to_create = {}
    for (spo_number, product_id, warehouse_id), items in groups.items():
        existing = db.query(SPOAllocation).filter(
            SPOAllocation.spo_number == spo_number,
            SPOAllocation.product_id == product_id,
            SPOAllocation.warehouse_id == warehouse_id,
        ).first()
        if existing:
            first = items[0]
            validation_errors.append(
                _ValidationError(
                    item_index=0,  # group-level: use spo_number + product_code to identify
                    spo_number=spo_number,
                    product_code=first.product_code,
                    reason="SPO number, product and warehouse combination already exists",
                )
            )
        else:
            groups_to_create[(spo_number, product_id, warehouse_id)] = items

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    code_by_product_id = {}
    allocations = []
    for (spo_number, product_id, warehouse_id), items in groups_to_create.items():
        first = items[0]
        product = products_map[normalize_code(first.product_code)]
        code_by_product_id[product_id] = product.product_code
        total_qty = sum(
            (item.quantity if item.quantity is not None else item.allocated_quantity) or 0
            for item in items
        )

        if first.inbound_shipment_id:
            inbound_shipment_id = first.inbound_shipment_id
        else:
            cn = (first.shipping_container_number or "").strip()
            inbound_shipment_id = shipment_by_container[normalize_code(cn)].id

        allocations.append(
            SPOAllocation(
                spo_number=spo_number,
                spo_line_number=None,
                inbound_shipment_id=inbound_shipment_id,
                warehouse_id=warehouse_id,
                storage_zone_id=first.storage_zone_id,
                allocated_quantity=total_qty,
                uom_id=first.uom_id,
                receipt_status=first.receipt_status or "pending",
                quantity_received=first.quantity_received or 0,
                quantity_rejected=first.quantity_rejected or 0,
                allocation_notes=first.allocation_notes,
                product_id=product_id,
                created_by=created_by,
            )
        )

    if allocations:
        db.add_all(allocations)
        db.commit()
        for allocation in allocations:
            db.refresh(allocation)
        inbound_svc = InboundShipmentService(db)
        for shipment_id in {
            allocation.inbound_shipment_id
            for allocation in allocations
            if allocation.inbound_shipment_id
        }:
            inbound_svc.refresh_shipment_line_statuses(shipment_id)

    return {
        "data": [
            {
                "id": allocation.id,
                "spo_number": allocation.spo_number,
                "product_id": allocation.product_id,
                "product_code": code_by_product_id.get(allocation.product_id),
            }
            for allocation in allocations
        ],
        "validation_errors": [
            {
                "item_index": ve.item_index,
                "spo_number": ve.spo_number,
                "product_code": ve.product_code,
                "reason": ve.reason,
            }
            for ve in validation_errors
        ],
    }
