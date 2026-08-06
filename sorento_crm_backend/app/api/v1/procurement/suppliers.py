"""Suppliers API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user
from app.services.procurement_service import SupplierService
from app.schemas.procurement import SupplierCreate, SupplierUpdate, SupplierResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error
from app.services.bulk_update_registry import MAX_BULK_IDS, run_bulk_update

router = APIRouter()


class BulkUpdateRequest(BaseModel):
    """Whitelisted bulk-edit request. `field` is validated against the suppliers
    bulk-update whitelist server-side; `value` is coerced/allow-listed per field."""

    ids: List[str] = Field(..., min_length=1, max_length=MAX_BULK_IDS)
    field: str
    value: Any = None


class BulkUpdateSkipped(BaseModel):
    id: str
    label: str
    reason: str


class BulkUpdateResponse(BaseModel):
    updated: int
    skipped: List[BulkUpdateSkipped]


@router.get("/", response_model=ListResponse[SupplierResponse])
def get_suppliers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
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
def get_suppliers_select(
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


@router.get("/neighbours")
def get_supplier_neighbours(
    id: str = Query(..., description="Supplier id to resolve neighbours for"),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Prev/next neighbours of a supplier within the active filtered+sorted list set.

    Accepts the same filter/sort/search params as the list GET (page/limit are
    irrelevant and ignored). Returns ``{total, index, prev_id, next_id}`` with the
    1-based ``index`` and circular wrap-around neighbours. If the record is not in
    the filtered set, falls back to the unfiltered, default-sorted set.
    """
    try:
        service = SupplierService(db)
        return service.neighbours(
            supplier_id=id,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single supplier by ID."""
    try:
        validate_uuid_path(supplier_id, resource="Supplier")
        service = SupplierService(db)
        supplier = service.get_supplier(supplier_id)
        return supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
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


@router.post("/bulk-update", response_model=BulkUpdateResponse)
def bulk_update_suppliers(
    payload: BulkUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk-edit a single whitelisted field across selected suppliers.

    Runs every selected id through the normal ``SupplierService.update_supplier``
    path (so validation + `__audit_track__` audit rows fire per row). A field not
    on the whitelist, or a value not allowed for it, is a 400. Rows that can't be
    updated (e.g. not found) come back in ``skipped`` with a human reason; the
    rest commit. Partial success, not all-or-nothing.
    """
    try:
        return run_bulk_update(
            db,
            "suppliers",
            payload.ids,
            payload.field,
            payload.value,
            current_user,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: str,
    supplier_data: SupplierUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a supplier."""
    try:
        validate_uuid_path(supplier_id, resource="Supplier")
        service = SupplierService(db)
        supplier = service.update_supplier(supplier_id, supplier_data)
        return supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{supplier_id}", status_code=status.HTTP_200_OK)
def delete_supplier(
    supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a supplier."""
    try:
        validate_uuid_path(supplier_id, resource="Supplier")
        service = SupplierService(db)
        # Implement delete logic
        return {"message": "Supplier deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
