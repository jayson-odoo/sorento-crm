"""External API for product attachment linking."""
import html
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.attachments import (
    ProductAttachmentLinkRequest,
    ProductAttachmentLinkRequestAny,
    ProductAttachmentBulkLinkRequest,
    ProductAttachmentBulkLinkResponse,
    ProductAttachmentBulkLinkItem,
)
from app.schemas.product import ProductAttachmentCreate, ProductAttachmentResponse
from app.services.product_service import ProductAttachmentService
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.services.attachment_notification_helper import (
    build_attachment_detail_url,
    build_product_detail_url,
    notify_after_external_attachment_entity,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _notify_product_attachment_external(
    db: Session,
    *,
    attachment_id: str,
    notify_user_id: str | None,
    mode: str,
    product_code: str | None = None,
    product_id: str | None = None,
    linked_codes: list[str] | None = None,
) -> None:
    """Notify attachment uploaders / notify_user_id after successful external product–attachment link."""
    if mode == "single" and product_id and product_code is not None:
        pc = product_code or "—"
        summary_plain = (
            f'Your file was linked to product "{pc}" in Sorento CRM'
        )
        summary_html = (
            f"<p>Your file was linked to product <strong>{html.escape(pc)}</strong> in Sorento CRM.</p>"
        )
        notify_after_external_attachment_entity(
            db,
            [attachment_id],
            notify_user_id,
            notif_type="external_product_attachment_linked",
            title=f"Product attachment linked: {pc}",
            summary_plain=summary_plain,
            summary_html=summary_html,
            entity_url=build_product_detail_url(str(product_id)),
            entity_link_text="Open product in Sorento CRM",
        )
        return

    if mode == "bulk":
        codes = linked_codes or []
        codes_str = ", ".join(codes[:30]) if codes else "—"
        summary_plain = (
            "Your file was linked to product(s) in Sorento CRM "
            f"Products: {codes_str}."
        )
        summary_html = (
            "<p>Your file was linked to product(s) in Sorento CRM "
            f"<p>Products: <strong>{html.escape(codes_str)}</strong>.</p>"
        )
        notify_after_external_attachment_entity(
            db,
            [attachment_id],
            notify_user_id,
            notif_type="external_product_attachment_linked",
            title="Product attachment(s) linked",
            summary_plain=summary_plain,
            summary_html=summary_html,
            entity_url=build_attachment_detail_url(attachment_id),
            entity_link_text="View attachment in Sorento CRM",
        )


def _normalize_product_code(s: str) -> str:
    """Remove spaces and normalize for matching (case-insensitive)."""
    if not s:
        return ""
    return (s or "").replace(" ", "").strip().lower()


@router.post("/")
def create_product_attachment(
    payload: ProductAttachmentLinkRequestAny,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Link an attachment to one product (product_code) or many (products).
    For bulk, products are matched by product_code after removing spaces (e.g. "WC 8038" matches "WC8038").
    """
    attachment = db.query(Attachment).filter(Attachment.id == payload.attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attachment_id",
        )

    if payload.get_use_bulk():
        return _link_attachment_to_products_bulk(
            db,
            payload.attachment_id,
            payload.products or [],
            current_user,
            payload.access_levels,
            notify_user_id=getattr(payload, "notify_user_id", None),
            field_keys_override=getattr(payload, "field_keys", None),
        )

    # Single link: ILIKE search on product_code (input: spaces removed, then used as pattern)
    normalized = _normalize_product_code(payload.product_code or "")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product_code",
        )
    product = db.query(Product).filter(
        Product.product_code.ilike(f"%{normalized}%")
    ).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product_code",
        )
    product_id = str(getattr(product, "id"))
    product_code = str(getattr(product, "product_code", "") or "")
    data = ProductAttachmentCreate(
        product_id=product_id,
        attachment_id=payload.attachment_id,
        sort_order=payload.sort_order,
        is_primary=payload.is_primary,
        access_levels=payload.access_levels,
    )
    service = ProductAttachmentService(db)
    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user["id"]
    result = service.create_product_attachment(data, created_by=created_by)
    try:
        AttachmentFieldLinkService(db).apply_template_to_row(
            attachment,
            "product",
            product_id,
            override_keys=payload.field_keys,
            created_by=created_by,
        )
        db.commit()
    except Exception as e:
        # Field-link fan-out must never fail the upstream link itself; the
        # link row is already committed and the user can recover via the
        # per-row Manage field links endpoint.
        logger.warning(
            "Field-link fan-out failed for attachment=%s product=%s: %s",
            payload.attachment_id,
            product_id,
            e,
            exc_info=True,
        )
    try:
        _notify_product_attachment_external(
            db,
            attachment_id=payload.attachment_id,
            notify_user_id=getattr(payload, "notify_user_id", None),
            mode="single",
            product_code=product_code,
            product_id=product_id,
        )
    except Exception as e:
        logger.warning("External product attachment notification failed: %s", e, exc_info=True)
    return result


def _link_attachment_to_products_bulk(
    db: Session,
    attachment_id: str,
    products: list[str],
    current_user: dict,
    access_levels: list[str] | None = None,
    notify_user_id: str | None = None,
    field_keys_override: list[str] | None = None,
) -> ProductAttachmentBulkLinkResponse:
    service = ProductAttachmentService(db)
    field_link_service = AttachmentFieldLinkService(db)
    attachment_row = (
        db.query(Attachment).filter(Attachment.id == attachment_id).first()
    )
    # The integration's principal is a real users row, so attribution is recorded.
    created_by = current_user["id"]
    linked: list[ProductAttachmentBulkLinkItem] = []
    skipped_product_codes: list[str] = []
    already_linked: list[str] = []
    seen_normalized: set[str] = set()

    for raw_code in products:
        code = (raw_code or "").strip()
        if not code:
            continue
        normalized = _normalize_product_code(code)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)

        product = db.query(Product).filter(
            Product.product_code.ilike(f"%{normalized}%")
        ).first()
        if not product:
            skipped_product_codes.append(code)
            continue

        existing = db.query(ProductAttachment).filter(
            ProductAttachment.attachment_id == attachment_id,
            ProductAttachment.product_id == product.id,
        ).first()
        product_id = str(getattr(product, "id"))
        product_code = str(getattr(product, "product_code", "") or "")
        if existing:
            already_linked.append(product_code or code)
            continue

        data = ProductAttachmentCreate(
            product_id=product_id,
            attachment_id=attachment_id,
            access_levels=access_levels,
        )
        service.create_product_attachment(data, created_by=created_by)
        try:
            field_link_service.apply_template_to_row(
                attachment_row or attachment_id,
                "product",
                product_id,
                override_keys=field_keys_override,
                created_by=created_by,
            )
            db.commit()
        except Exception as e:
            logger.warning(
                "Field-link fan-out failed for attachment=%s product=%s: %s",
                attachment_id,
                product_id,
                e,
                exc_info=True,
            )
        linked.append(
            ProductAttachmentBulkLinkItem(product_id=product_id, product_code=product_code or code)
        )

    try:
        codes = [x.product_code for x in linked] + list(already_linked)
        _notify_product_attachment_external(
            db,
            attachment_id=attachment_id,
            notify_user_id=notify_user_id,
            mode="bulk",
            linked_codes=codes,
        )
    except Exception as e:
        logger.warning("External product attachment bulk notification failed: %s", e, exc_info=True)

    return ProductAttachmentBulkLinkResponse(
        attachment_id=attachment_id,
        linked=linked,
        skipped_product_codes=skipped_product_codes,
        already_linked=already_linked,
    )


@router.post(
    "/link-products",
    response_model=ProductAttachmentBulkLinkResponse,
    status_code=status.HTTP_200_OK,
)
def link_attachment_to_products(
    payload: ProductAttachmentBulkLinkRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Link one attachment to many products by product code.
    Products are matched by product_code after removing spaces (e.g. "WC 8038" matches "WC8038").
    """
    attachment = db.query(Attachment).filter(Attachment.id == payload.attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attachment_id",
        )
    return _link_attachment_to_products_bulk(
        db,
        payload.attachment_id,
        payload.products,
        current_user,
        payload.access_levels,
        notify_user_id=getattr(payload, "notify_user_id", None),
        field_keys_override=getattr(payload, "field_keys", None),
    )
