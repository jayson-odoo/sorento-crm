"""External API for product attachment linking."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import (
    ProductAttachmentLinkRequest,
    ProductAttachmentLinkRequestAny,
    ProductAttachmentBulkLinkRequest,
    ProductAttachmentBulkLinkResponse,
    ProductAttachmentBulkLinkItem,
)
from app.schemas.product import ProductAttachmentCreate, ProductAttachmentResponse
from app.services.product_service import ProductAttachmentService
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment

router = APIRouter()


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
            db, payload.attachment_id, payload.products or [], current_user, payload.access_levels
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
    data = ProductAttachmentCreate(
        product_id=product.id,
        attachment_id=payload.attachment_id,
        sort_order=payload.sort_order,
        is_primary=payload.is_primary,
        access_levels=payload.access_levels,
    )
    service = ProductAttachmentService(db)
    return service.create_product_attachment(
        data, created_by=None if current_user.get("id") == "system" else current_user["id"]
    )


def _link_attachment_to_products_bulk(
    db: Session,
    attachment_id: str,
    products: list[str],
    current_user: dict,
    access_levels: list[str] | None = None,
) -> ProductAttachmentBulkLinkResponse:
    service = ProductAttachmentService(db)
    created_by = None if current_user.get("id") == "system" else current_user["id"]
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
        if existing:
            already_linked.append(product.product_code or code)
            continue

        data = ProductAttachmentCreate(
            product_id=product.id,
            attachment_id=attachment_id,
            access_levels=access_levels,
        )
        service.create_product_attachment(data, created_by=created_by)
        linked.append(ProductAttachmentBulkLinkItem(product_id=product.id, product_code=product.product_code or code))

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
        db, payload.attachment_id, payload.products, current_user, payload.access_levels
    )
