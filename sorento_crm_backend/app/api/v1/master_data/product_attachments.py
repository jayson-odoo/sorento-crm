"""Product attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.product_service import ProductAttachmentService
from app.services.uuid_list_param import parse_uuid_list
from app.schemas.product import ProductAttachmentCreate, ProductAttachmentUpdate, ProductAttachmentResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ProductAttachmentResponse])
async def get_product_attachments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    query: Optional[str] = Query(None, description="Free-text search: product code/name, filename, attachment type."),
    entities: Optional[list[str]] = Query(
        None,
        description="DEPRECATED — free-text entity bag. Prefer `product_ids` / `attachment_ids`.",
    ),
    product_ids: Optional[list[str]] = Query(
        None,
        description="Canonical product UUIDs (csv/JSON/repeated).",
    ),
    attachment_ids: Optional[list[str]] = Query(
        None,
        description="Canonical attachment UUIDs (csv/JSON/repeated).",
    ),
    attachment_type_ids: Optional[list[str]] = Query(
        None,
        description="Canonical AttachmentType UUIDs (csv/JSON/repeated) — narrows to brochure/spec sheet/installation guide/etc.",
    ),
    product_id: Optional[str] = Query(None, description="Legacy: single product UUID."),
    attachment_id: Optional[str] = Query(None, description="Legacy: single attachment UUID."),
    user_type: Optional[str] = Query(None, description="Legacy single access-level filter."),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get product attachments with pagination and filtering."""
    try:
        service = ProductAttachmentService(db)
        from app.services.entity_filter_helpers import normalize_entities_query_param
        result = service.list_product_attachments(
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            product_id=product_id,
            attachment_id=attachment_id,
            product_ids=parse_uuid_list(product_ids, param_name="product_ids"),
            attachment_ids=parse_uuid_list(attachment_ids, param_name="attachment_ids"),
            attachment_type_ids=parse_uuid_list(attachment_type_ids, param_name="attachment_type_ids"),
            query=query,
            user_type=user_type,
            contact_access_codes=None,
            entities=normalize_entities_query_param(entities),
        )
        # Entity-axis relaxation (§3.4 M5): when the service attached `alternatives`
        # / `relaxed_axis` (only on an empty result), bypass the strict
        # `ListResponse` response_model — which would silently drop those keys — and
        # emit the raw dict. `data` is always [] here so encoding is trivial, and the
        # with-data path stays byte-identical (AC-R1).
        if isinstance(result, dict) and result.get("alternatives"):
            from fastapi.responses import JSONResponse
            from fastapi.encoders import jsonable_encoder
            return JSONResponse(content=jsonable_encoder(result))
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
        validate_uuid_path(product_attachment_id, resource="Product Attachment")
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
        validate_uuid_path(product_attachment_id, resource="Product Attachment")
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
        validate_uuid_path(product_attachment_id, resource="Product Attachment")
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
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get all attachments for a specific product."""
    try:
        service = ProductAttachmentService(db)
        product_attachments = service.get_product_attachments_by_product(
            product_id,
            user_type=user_type,
            contact_access_codes=None,
        )
        return product_attachments
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
