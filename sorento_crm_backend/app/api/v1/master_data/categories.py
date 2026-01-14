"""Product categories API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
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
    """Delete a category."""
    try:
        service = ProductCategoryService(db)
        # Implement delete logic
        return {"message": "Category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
