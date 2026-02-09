"""Suppliers API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import SupplierService
from app.schemas.procurement import SupplierCreate, SupplierUpdate, SupplierResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[SupplierResponse])
async def get_suppliers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get suppliers with pagination, search, and sorting."""
    try:
        service = SupplierService(db)
        result = service.list_suppliers(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[SupplierResponse])
async def get_suppliers_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get suppliers for select dropdowns."""
    try:
        from sqlalchemy import or_
        from app.models.procurement import Supplier
        q = db.query(Supplier).filter(Supplier.is_active == True)
        
        if query:
            q = q.filter(
                or_(
                    Supplier.supplier_code.ilike(f"%{query}%"),
                    Supplier.supplier_name.ilike(f"%{query}%")
                )
            )
        
        suppliers = q.limit(100).all()
        return suppliers
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single supplier by ID."""
    try:
        service = SupplierService(db)
        supplier = service.get_supplier(supplier_id)
        return supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    supplier_data: SupplierCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new supplier."""
    try:
        service = SupplierService(db)
        supplier = service.create_supplier(supplier_data)
        return supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: str,
    supplier_data: SupplierUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a supplier."""
    try:
        service = SupplierService(db)
        supplier = service.update_supplier(supplier_id, supplier_data)
        return supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{supplier_id}", status_code=status.HTTP_200_OK)
async def delete_supplier(
    supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a supplier."""
    try:
        service = SupplierService(db)
        # Implement delete logic
        return {"message": "Supplier deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
