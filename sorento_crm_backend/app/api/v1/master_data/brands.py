"""Brands API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.services.product_service import BrandService
from app.schemas.product import BrandCreate, BrandUpdate, BrandResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from app.services.uuid_list_param import parse_uuid_list

router = APIRouter()


@router.get("/", response_model=ListResponse[BrandResponse])
async def get_brands(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    brand_ids: Optional[List[str]] = Query(
        None,
        description="Filter by canonical brand UUIDs (repeated / csv / JSON array).",
    ),
    product_ids: Optional[List[str]] = Query(
        None,
        description="Filter to the brands of these product UUIDs (repeated / csv / JSON array).",
    ),
    current_user: dict = Depends(require_permission_with_api_key("master_data.brands.view")),
    db: Session = Depends(get_db)
):
    """Get brands with pagination and search."""
    try:
        service = BrandService(db)
        result = service.list_brands(
            page=page,
            limit=limit,
            query=query,
            brand_ids=parse_uuid_list(brand_ids, param_name="brand_ids"),
            product_ids=parse_uuid_list(product_ids, param_name="product_ids"),
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[BrandResponse])
async def get_brands_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.brands.view")),
    db: Session = Depends(get_db)
):
    """Get brands for select dropdowns."""
    try:
        from sqlalchemy import or_
        from app.models.product import Brand
        q = db.query(Brand).filter(Brand.is_active == True)
        
        if query:
            q = q.filter(
                or_(
                    Brand.brand_code.ilike(f"%{query}%"),
                    Brand.brand_name.ilike(f"%{query}%")
                )
            )
        
        brands = q.limit(100).all()
        return brands
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.brands.view")),
    db: Session = Depends(get_db)
):
    """Get a single brand by ID."""
    try:
        service = BrandService(db)
        brand = service.get_brand(brand_id)
        return brand
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    brand_data: BrandCreate,
    current_user: dict = Depends(require_permission("master_data.brands.add")),
    db: Session = Depends(get_db)
):
    """Create a new brand."""
    try:
        service = BrandService(db)
        brand = service.create_brand(brand_data)
        return brand
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: str,
    brand_data: BrandUpdate,
    current_user: dict = Depends(require_permission("master_data.brands.edit")),
    db: Session = Depends(get_db)
):
    """Update a brand."""
    try:
        service = BrandService(db)
        brand = service.update_brand(brand_id, brand_data)
        return brand
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{brand_id}", status_code=status.HTTP_200_OK)
async def delete_brand(
    brand_id: str,
    current_user: dict = Depends(require_permission("master_data.brands.delete")),
    db: Session = Depends(get_db)
):
    """Delete a brand."""
    try:
        service = BrandService(db)
        return service.delete_brand(brand_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
