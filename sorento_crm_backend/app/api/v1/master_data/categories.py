"""Product categories API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user
from app.services.product_service import ProductCategoryService
from app.schemas.product import ProductCategoryCreate, ProductCategoryUpdate, ProductCategoryResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/tree")
async def get_categories_tree(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product categories as a tree structure."""
    try:
        service = ProductCategoryService(db)
        tree = service.get_categories_tree()
        return tree
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_categories_tree: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[ProductCategoryResponse])
async def get_categories(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product categories with pagination and search."""
    try:
        service = ProductCategoryService(db)
        result = service.list_categories(page=page, limit=limit, query=query)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[ProductCategoryResponse])
async def get_categories_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product categories for select dropdowns."""
    try:
        from sqlalchemy import or_
        from app.models.product import ProductCategory
        q = db.query(ProductCategory).filter(ProductCategory.is_active == True)
        
        if query:
            q = q.filter(
                or_(
                    ProductCategory.category_code.ilike(f"%{query}%"),
                    ProductCategory.category_name.ilike(f"%{query}%")
                )
            )
        q = q.order_by(ProductCategory.display_order.asc(), ProductCategory.category_name.asc())
        categories = q.limit(100).all()
        return categories
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{category_id}", response_model=ProductCategoryResponse)
async def get_category(
    category_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single category by ID."""
    try:
        service = ProductCategoryService(db)
        category = service.get_category(category_id)
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ProductCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: ProductCategoryCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new category."""
    try:
        service = ProductCategoryService(db)
        category = service.create_category(category_data)
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{category_id}", response_model=ProductCategoryResponse)
async def update_category(
    category_id: str,
    category_data: ProductCategoryUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a category."""
    try:
        service = ProductCategoryService(db)
        category = service.update_category(category_id, category_data)
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
async def delete_category(
    category_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a category. Fails with 409 if any products use this category."""
    try:
        service = ProductCategoryService(db)
        service.delete_category(category_id)
        return {"message": "Category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
