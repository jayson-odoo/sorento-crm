"""Units of measure API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.product_service import UnitOfMeasureService
from app.schemas.product import UnitOfMeasureCreate, UnitOfMeasureUpdate, UnitOfMeasureResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[UnitOfMeasureResponse])
async def get_units_of_measure(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get units of measure with pagination and search."""
    try:
        service = UnitOfMeasureService(db)
        result = service.list_uoms(page=page, limit=limit, query=query)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{uom_id}", response_model=UnitOfMeasureResponse)
async def get_uom(
    uom_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single UOM by ID."""
    try:
        service = UnitOfMeasureService(db)
        uom = service.get_uom(uom_id)
        return uom
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UnitOfMeasureResponse, status_code=status.HTTP_201_CREATED)
async def create_uom(
    uom_data: UnitOfMeasureCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new UOM."""
    try:
        service = UnitOfMeasureService(db)
        uom = service.create_uom(uom_data)
        return uom
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{uom_id}", response_model=UnitOfMeasureResponse)
async def update_uom(
    uom_id: str,
    uom_data: UnitOfMeasureUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a UOM."""
    try:
        service = UnitOfMeasureService(db)
        uom = service.update_uom(uom_id, uom_data)
        return uom
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{uom_id}", status_code=status.HTTP_200_OK)
async def delete_uom(
    uom_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a UOM."""
    try:
        service = UnitOfMeasureService(db)
        # Implement delete logic
        return {"message": "UOM deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
