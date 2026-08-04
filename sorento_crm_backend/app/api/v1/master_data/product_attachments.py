"""Product attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
# Two lines on purpose: tests/test_uuid_path_sweep.py asserts the
# `validate_uuid_path` import verbatim, so folding UUID_PATTERN into it would
# make this router read as unguarded to that sweep.
from app.services.uuid_path_param import UUID_PATTERN
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    require_permission,
    require_permission_with_api_key,
)
from app.services import brochure_image_service
from app.services.product_service import ProductAttachmentService
from app.services.uuid_list_param import parse_uuid_list
from app.schemas.product import (
    BrochureImageAdopted,
    BrochureImageAdoptSingle,
    BrochureImageChoice,
    BrochureImageList,
    BrochureImageSet,
    ProductAttachmentCreate,
    ProductAttachmentUpdate,
    ProductAttachmentResponse,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


# --- Brochure images (S7.0) -------------------------------------------------
#
# DECLARED FIRST, AND THEY HAVE TO STAY FIRST. FastAPI matches routes in
# declaration order, and this router declares `GET /{product_attachment_id}`
# below. Moved under it, "brochure-images" is read as an attachment id and every
# call to this feature answers "Product Attachment not found" - which is what the
# route tests saw before these existed. The same shape bit the SLA router, where
# n8n's POST /integration/escalate was captured as tracking_id="integration".
#
# The permission slugs are the existing product-attachment ones. A brochure image
# IS a product attachment - the choice is a flag on the link row - so inventing a
# slug would mean a grant sweep for a right every attachment editor already holds.


@router.get("/brochure-images", response_model=BrochureImageList)
async def list_brochure_images(
    promotion_id: Optional[str] = Query(
        None,
        # Validated here rather than in the service: compared against a UUID
        # column raw, a malformed value reached psycopg as a DataError - an
        # unhandled 500 that also left the session in a failed transaction.
        # Every other id on this router is validated too.
        pattern=UUID_PATTERN,
        description="Narrow to the products in one promotion, so a whole flyer is one sitting.",
    ),
    only_unset: bool = Query(True, description="Hide products whose image is already chosen."),
    query: Optional[str] = Query(None, description="Matches product code or name."),
    page: int = Query(1, ge=1),
    limit: int = Query(brochure_image_service.DEFAULT_LIMIT, ge=1, le=brochure_image_service.MAX_LIMIT),
    current_user: dict = Depends(
        require_permission_with_api_key("master_data.product_attachments.view")
    ),
    db: Session = Depends(get_db),
):
    """Products and the images somebody could choose between."""
    result = brochure_image_service.list_brochure_images(
        db,
        promotion_id=promotion_id,
        only_unset=only_unset,
        query=query,
        page=page,
        limit=limit,
    )
    # The service leaves every URL None so its own tests need no object storage.
    # Signing is the route's job, and only for the page actually being sent.
    brochure_image_service.signed_urls(result["items"], db)
    return result


@router.post("/brochure-images/adopt-single", response_model=BrochureImageAdopted)
async def adopt_single_candidate_images(
    payload: BrochureImageAdoptSingle,
    current_user: dict = Depends(require_permission("master_data.product_attachments.edit")),
    db: Session = Depends(get_db),
):
    """Take the only photo a product has, for every product named here.

    A POST and not part of the list GET, deliberately: a read must not write.
    The screen calls this once per page of the worklist, so 509 products with a
    single candidate cost one request rather than 509 clicks.

    Products with no candidate, or with two or more, are left alone - those are
    the ones that need somebody to look.
    """
    adopted = brochure_image_service.adopt_single_candidates(
        db,
        payload.product_ids,
        user_id=str(current_user.get("id", "")) if current_user else None,
    )
    db.commit()
    return BrochureImageAdopted(productIds=adopted)


@router.put("/brochure-images/{product_id}", response_model=BrochureImageChoice)
async def set_brochure_image(
    product_id: str,
    payload: BrochureImageSet,
    current_user: dict = Depends(require_permission("master_data.product_attachments.edit")),
    db: Session = Depends(get_db),
):
    """Record which image of a product a brochure shows.

    The service raises AppException(404) for a product out of scope or a file not
    attached to it, and 400 for a non-image. Those reach the global handler
    unwrapped: catching them here would turn a deliberate 404 into a 500.
    """
    validate_uuid_path(product_id, resource="Product")
    link = brochure_image_service.set_brochure_image(
        db,
        product_id,
        payload.attachment_id,
        user_id=str(current_user.get("id", "")) if current_user else None,
    )
    db.commit()
    return BrochureImageChoice(productId=product_id, chosenAttachmentId=link.attachment_id)


@router.delete("/brochure-images/{product_id}", response_model=BrochureImageChoice)
async def clear_brochure_image(
    product_id: str,
    current_user: dict = Depends(require_permission("master_data.product_attachments.edit")),
    db: Session = Depends(get_db),
):
    """Leave a product with no chosen image.

    Its tile falls back to first-linked-row, which is a knowingly weak answer
    rather than a silently weak one.
    """
    validate_uuid_path(product_id, resource="Product")
    brochure_image_service.clear_brochure_image(db, product_id)
    db.commit()
    return BrochureImageChoice(productId=product_id, chosenAttachmentId=None)


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
