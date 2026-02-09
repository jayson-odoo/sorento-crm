"""Packing lists (Inbound Shipments) API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import InboundShipmentService
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentUpdate, InboundShipmentResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


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
    """Get a single packing list by ID."""
    try:
        service = InboundShipmentService(db)
        shipment = service.get_shipment(shipment_id)
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
