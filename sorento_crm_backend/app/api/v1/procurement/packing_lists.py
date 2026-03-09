"""Packing lists (Inbound Shipments) API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.procurement import SPOAllocation
from app.services.procurement_service import InboundShipmentService
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentUpdate, InboundShipmentResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


class BulkDeletePackingListsRequest(BaseModel):
    ids: list[str]


@router.get("/", response_model=ListResponse[InboundShipmentResponse])
async def get_packing_lists(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    shipment_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get packing lists (inbound shipments) with pagination, filtering, and sorting."""
    try:
        service = InboundShipmentService(db)
        result = service.list_shipments(
            page=page,
            limit=limit,
            query=query,
            supplier_id=supplier_id,
            shipment_status=shipment_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{shipment_id}", response_model=InboundShipmentResponse)
async def get_packing_list(
    shipment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single packing list by ID. Shipment lines include spo_allocated_quantity, quantity_received, and line_status (stored in DB for n8n/API)."""
    try:
        service = InboundShipmentService(db)
        shipment = service.get_shipment(shipment_id)
        # Refresh and persist line_status so n8n/API always have current value in DB
        service.refresh_shipment_line_statuses(shipment_id)
        # Reload shipment so line_status is in memory (refresh committed)
        shipment = service.get_shipment(shipment_id)
        # SPO allocated total per product on this shipment
        totals = (
            db.query(SPOAllocation.product_id, func.sum(SPOAllocation.allocated_quantity).label("total"))
            .filter(SPOAllocation.inbound_shipment_id == shipment_id)
            .group_by(SPOAllocation.product_id)
            .all()
        )
        spo_by_product = {str(p): int(t) for p, t in totals}
        # Quantity received per inbound_shipment_line (SPO allocations are keyed by inbound_shipment_lines_id)
        received_by_line = (
            db.query(SPOAllocation.inbound_shipment_lines_id, func.sum(SPOAllocation.quantity_received).label("total"))
            .filter(SPOAllocation.inbound_shipment_id == shipment_id)
            .filter(SPOAllocation.inbound_shipment_lines_id.isnot(None))
            .group_by(SPOAllocation.inbound_shipment_lines_id)
            .all()
        )
        received_by_line_id = {str(line_id): int(t) for line_id, t in received_by_line}
        for line in shipment.shipment_lines:
            setattr(line, "spo_allocated_quantity", spo_by_product.get(str(line.product_id), 0))
            setattr(line, "quantity_received", received_by_line_id.get(str(line.id), 0))
        return shipment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=InboundShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_packing_list(
    shipment_data: InboundShipmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new packing list (inbound shipment) with lines."""
    try:
        service = InboundShipmentService(db)
        shipment = service.create_shipment(shipment_data, current_user["id"])
        return shipment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{shipment_id}", response_model=InboundShipmentResponse)
async def update_packing_list(
    shipment_id: str,
    shipment_data: InboundShipmentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a packing list."""
    try:
        service = InboundShipmentService(db)
        shipment = service.update_shipment(shipment_id, shipment_data, current_user["id"])
        return shipment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_packing_lists(
    body: BulkDeletePackingListsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk delete packing lists (inbound shipments) by ID."""
    try:
        service = InboundShipmentService(db)
        return service.bulk_delete_shipments(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{shipment_id}", status_code=status.HTTP_200_OK)
async def delete_packing_list(
    shipment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a packing list (inbound shipment). Lines and SPO allocations cascade."""
    try:
        service = InboundShipmentService(db)
        service.delete_shipment(shipment_id)
        return {"message": "Packing list deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
