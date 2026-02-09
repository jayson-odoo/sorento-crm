"""Product attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.product_service import ProductAttachmentService
from app.schemas.product import ProductAttachmentCreate, ProductAttachmentUpdate, ProductAttachmentResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ProductAttachmentResponse])
async def get_product_attachments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    product_id: Optional[str] = Query(None),
    attachment_id: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product attachments with pagination and filtering."""
    try:
        service = ProductAttachmentService(db)
        result = service.list_product_attachments(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            product_id=product_id,
            attachment_id=attachment_id,
            user_type=user_type
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_attachment_id}", response_model=ProductAttachmentResponse)
async def get_product_attachment(
    product_attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single product attachment by ID."""
    try:
        service = ProductAttachmentService(db)
        product_attachment = service.get_product_attachment(product_attachment_id)
        return product_attachment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ProductAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_product_attachment(
    product_attachment_data: ProductAttachmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product attachment relationship."""
    try:
        service = ProductAttachmentService(db)
        created_by = str(current_user.get("id", "")) if current_user else None
        product_attachment = service.create_product_attachment(product_attachment_data, created_by=created_by)
        return product_attachment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{product_attachment_id}", response_model=ProductAttachmentResponse)
async def update_product_attachment(
    product_attachment_id: str,
    product_attachment_data: ProductAttachmentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a product attachment relationship."""
    try:
        service = ProductAttachmentService(db)
        product_attachment = service.update_product_attachment(product_attachment_id, product_attachment_data)
        return product_attachment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{product_attachment_id}", status_code=status.HTTP_200_OK)
async def delete_product_attachment(
    product_attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a product attachment relationship."""
    try:
        service = ProductAttachmentService(db)
        service.delete_product_attachment(product_attachment_id)
        return {"message": "Product attachment deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/product/{product_id}")
async def get_product_attachments_by_product(
    product_id: str,
    user_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all attachments for a specific product."""
    try:
        service = ProductAttachmentService(db)
        product_attachments = service.get_product_attachments_by_product(product_id, user_type=user_type)
        return product_attachments
    except Exception as e:
        raise handle_internal_error(str(e))
