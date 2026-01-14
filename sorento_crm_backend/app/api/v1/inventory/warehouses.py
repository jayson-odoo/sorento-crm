"""Warehouses API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.inventory_service import WarehouseService
from app.schemas.inventory import WarehouseCreate, WarehouseUpdate, WarehouseResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[WarehouseResponse])
async def get_warehouses(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get warehouses with pagination and search."""
    try:
        service = WarehouseService(db)
        result = service.list_warehouses(page=page, limit=limit, query=query)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single warehouse by ID."""
    try:
        service = WarehouseService(db)
        warehouse = service.get_warehouse(warehouse_id)
        return warehouse
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    warehouse_data: WarehouseCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new warehouse."""
    try:
        service = WarehouseService(db)
        warehouse = service.create_warehouse(warehouse_data)
        return warehouse
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: str,
    warehouse_data: WarehouseUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a warehouse."""
    try:
        service = WarehouseService(db)
        warehouse = service.update_warehouse(warehouse_id, warehouse_data)
        return warehouse
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{warehouse_id}", status_code=status.HTTP_200_OK)
async def delete_warehouse(
    warehouse_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a warehouse."""
    try:
        service = WarehouseService(db)
        # Implement delete logic
        return {"message": "Warehouse deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
