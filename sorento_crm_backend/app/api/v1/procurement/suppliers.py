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
async def get_suppliers(
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


@router.get("/select")
async def get_suppliers_select(
    query: Optional[str] = Query(None),
    page: Optional[int] = Query(
        None, ge=1, description="Enables paging; omitted, the legacy bare array is returned."
    ),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Suppliers for select dropdowns, ordered by name then code.

    `page` is optional for backward compatibility with any other caller of this endpoint.
    Omitted, this returns the legacy bare array (capped at 100) - the PI list filter and the
    incoming-containers filter want the whole list at once, not a picker. Passed, it pages
    (`limit`, default 50, capped at `MAX_PAGE_LIMIT` - same ceiling as every other DataGrid
    list endpoint, `test_list_pagination_limit.py`) and returns `{items, has_more}` so a
    picker (the PI upload dialog, the loading plan container dialog) can offer Load more past
    the first page - two suppliers sharing a name (a real duplicate-data case) no longer land
    in an arbitrary order, and a tenant with hundreds of suppliers can reach all of them.
    """
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

        q = q.order_by(Supplier.supplier_name, Supplier.supplier_code)

        if page is None:
            suppliers = q.limit(100).all()
            return [SupplierResponse.model_validate(s) for s in suppliers]

        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit + 1).all()
        has_more = len(rows) > limit
        items = [SupplierResponse.model_validate(s) for s in rows[:limit]]
        return {"items": items, "has_more": has_more}
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
        validate_uuid_path(supplier_id, resource="Supplier")
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


@router.post("/bulk-update", response_model=BulkUpdateResponse)
async def bulk_update_suppliers(
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
async def update_supplier(
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
async def delete_supplier(
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
