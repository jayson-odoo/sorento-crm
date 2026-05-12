"""Product attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
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
    user_type: Optional[str] = Query(None, description="Legacy single access-level filter."),
    contact_id: Optional[str] = Query(None, description="Respond.io contact id (respond_io_id). Pair with space_id to filter by the contact's M2M access types."),
    space_id: Optional[str] = Query(None, description="Respond.io space id (respond_workspaces.space_id). Pair with contact_id."),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get product attachments with pagination and filtering."""
    try:
        from app.services.contact_access_type_service import ContactAccessTypeService
        contact_codes = ContactAccessTypeService(db).resolve_optional_contact_access_codes(contact_id, space_id)
        service = ProductAttachmentService(db)
        result = service.list_product_attachments(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            product_id=product_id,
            attachment_id=attachment_id,
            user_type=user_type,
            contact_access_codes=contact_codes,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_attachment_id}", response_model=ProductAttachmentResponse)
async def get_product_attachment(
    product_attachment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
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
        # Fan the attachment's field-linkage template (set at upload time) into
        # per-row attachment_field_links rows. Best-effort; never fail the link.
        try:
            from app.services.attachment_field_link_service import AttachmentFieldLinkService
            from app.models.resources import Attachment

            attachment_row = (
                db.query(Attachment)
                .filter(Attachment.id == product_attachment_data.attachment_id)
                .first()
            )
            AttachmentFieldLinkService(db).apply_template_to_row(
                attachment_row or product_attachment_data.attachment_id,
                "product",
                product_attachment_data.product_id,
                created_by=created_by,
            )
            db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Field-link fan-out failed for product=%s attachment=%s: %s",
                product_attachment_data.product_id,
                product_attachment_data.attachment_id,
                e,
                exc_info=True,
            )
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
    user_type: Optional[str] = Query(None, description="Legacy single access-level filter."),
    contact_id: Optional[str] = Query(None, description="Respond.io contact id (respond_io_id)."),
    space_id: Optional[str] = Query(None, description="Respond.io space id."),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get all attachments for a specific product."""
    try:
        from app.services.contact_access_type_service import ContactAccessTypeService
        contact_codes = ContactAccessTypeService(db).resolve_optional_contact_access_codes(contact_id, space_id)
        service = ProductAttachmentService(db)
        product_attachments = service.get_product_attachments_by_product(
            product_id,
            user_type=user_type,
            contact_access_codes=contact_codes,
        )
        return product_attachments
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
