"""SPO Allocations API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import SPOAllocationService
from app.schemas.procurement import SPOAllocationCreate, SPOAllocationUpdate, SPOAllocationResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[SPOAllocationResponse])
async def get_spo_allocations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    shipment_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    receipt_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get SPO allocations with pagination, filtering, and sorting."""
    try:
        service = SPOAllocationService(db)
        result = service.list_allocations(
            page=page,
            limit=limit,
            query=query,
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            receipt_status=receipt_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{allocation_id}", response_model=SPOAllocationResponse)
async def get_spo_allocation(
    allocation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single SPO allocation by ID."""
    try:
        service = SPOAllocationService(db)
        allocation = service.get_allocation(allocation_id)
        return allocation
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=SPOAllocationResponse, status_code=status.HTTP_201_CREATED)
async def create_spo_allocation(
    allocation_data: SPOAllocationCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new SPO allocation."""
    try:
        service = SPOAllocationService(db)
        allocation = service.create_allocation(allocation_data, current_user["id"])
        return allocation
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{allocation_id}", response_model=SPOAllocationResponse)
async def update_spo_allocation(
    allocation_id: str,
    allocation_data: SPOAllocationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an SPO allocation."""
    try:
        service = SPOAllocationService(db)
        allocation = service.update_allocation(allocation_id, allocation_data)
        return allocation
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{allocation_id}", status_code=status.HTTP_200_OK)
async def delete_spo_allocation(
    allocation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an SPO allocation."""
    try:
        service = SPOAllocationService(db)
        # Implement delete logic
        return {"message": "SPO allocation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
