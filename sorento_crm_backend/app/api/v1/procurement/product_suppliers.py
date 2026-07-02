"""Product suppliers API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user
from app.services.procurement_service import ProductSupplierService
from app.schemas.procurement import ProductSupplierCreate, ProductSupplierUpdate, ProductSupplierResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ProductSupplierResponse])
async def get_product_suppliers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    product_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product suppliers with pagination and filtering."""
    try:
        service = ProductSupplierService(db)
        result = service.list_product_suppliers(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            product_id=product_id,
            supplier_id=supplier_id
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_supplier_id}", response_model=ProductSupplierResponse)
async def get_product_supplier(
    product_supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single product supplier by ID."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        product_supplier = service.get_product_supplier(product_supplier_id)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ProductSupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_product_supplier(
    product_supplier_data: ProductSupplierCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product supplier relationship."""
    try:
        service = ProductSupplierService(db)
        product_supplier = service.create_product_supplier(product_supplier_data)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{product_supplier_id}", response_model=ProductSupplierResponse)
async def update_product_supplier(
    product_supplier_id: str,
    product_supplier_data: ProductSupplierUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a product supplier relationship."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        product_supplier = service.update_product_supplier(product_supplier_id, product_supplier_data)
        return product_supplier
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{product_supplier_id}", status_code=status.HTTP_200_OK)
async def delete_product_supplier(
    product_supplier_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a product supplier relationship."""
    try:
        validate_uuid_path(product_supplier_id, resource="Product Supplier")
        service = ProductSupplierService(db)
        service.delete_product_supplier(product_supplier_id)
        return {"message": "Product supplier deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/product/{product_id}")
async def get_product_suppliers_by_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all suppliers for a specific product."""
    try:
        service = ProductSupplierService(db)
        result = service.list_product_suppliers(
            page=1,
            limit=1000,
            product_id=product_id
        )
        # Return just the data array for this endpoint
        return result.get("data", [])
    except Exception as e:
        raise handle_internal_error(str(e))
