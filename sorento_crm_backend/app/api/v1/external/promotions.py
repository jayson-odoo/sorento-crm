"""External API for promotions."""
import logging
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PromotionRequest, PromotionCreateResponse
from app.schemas.marketing import PromotionResponse
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.resources import Attachment
from app.api.v1.external.utils import parse_date_value, get_products_by_code_exact
from app.services.marketing_service import (
    clamp_discount_percent_for_db,
    raise_promotion_product_unique_violation,
)
from app.services.attachment_notification_helper import notify_after_external_promotion_created

router = APIRouter()
logger = logging.getLogger(__name__)


def _attachment_ids_from_promotion_payload(payload: PromotionRequest) -> list[str]:
    """Root-level attachment_id and promotions.attachment_id list (same rules as create body)."""
    ids = list(payload.promotions.attachment_id or [])
    if payload.attachment_id and payload.attachment_id not in ids:
        ids.insert(0, payload.attachment_id)
    return ids


def _date_to_datetime(value: str | date) -> datetime:
    parsed = parse_date_value(value)
    if not parsed:
        raise ValueError("Invalid date")
    return datetime.combine(parsed, datetime.min.time())


@router.post("/", response_model=PromotionCreateResponse)
def create_promotion(
    payload: PromotionRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create a promotion linked to products. Body: { promotions: {...}, promotion_products: [...] }.
    Products are matched by exact product_code (trim only, no case change).
    If promo_code already exists, returns success with already_existed=true and conflict detail in message.
    Duplicate product codes in promotion_products: the first row per code is applied; later rows are skipped
    and listed in warnings (product_code and selling_price).

    Notifications (in-app + email, logged under Outgoing Mails):
    - Linked attachments: notifies each attachment uploader (uploaded_by) when attachment_id(s) are provided.
    - Optional notify_user_id: CRM user UUID to notify when the API key is system (created_by is null). Use n8n
      to pass the uploader from the attachment step. If omitted and uploaders cannot be resolved, no email is sent.
    """
    if not payload.promotion_products:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No promotion products provided")

    product_codes = [item.product_code for item in payload.promotion_products]
    products_map = get_products_by_code_exact(db, product_codes)
    missing_codes = [c for c in product_codes if (c or "").strip() not in products_map]
    # Missing product codes are a warning only: create the promotion and link only products that exist
    warnings = []
    if missing_codes:
        warnings.append({"message": "Missing product codes (exact match)", "product_codes": missing_codes})

    existing = db.query(Promotion).filter(Promotion.promo_code == payload.promotions.promo_code).first()
    if existing:
        db.refresh(existing)
        # Still notify uploaders (and optional notify_user_id) when the API is called with attachment_id(s),
        # e.g. n8n retries / resubmit with the same promo code — same as successful create path.
        try:
            notify_after_external_promotion_created(
                db,
                existing,
                _attachment_ids_from_promotion_payload(payload),
                payload.notify_user_id,
            )
        except Exception as e:
            logger.warning(
                "External promotion already_existed branch: notification failed: %s",
                e,
                exc_info=True,
            )
        return PromotionCreateResponse(
            promotion=PromotionResponse.model_validate(existing),
            already_existed=True,
            message="Promo code already exists.",
            warnings=warnings,
        )

    try:
        start_date = _date_to_datetime(payload.promotions.start_date)
        end_date = _date_to_datetime(payload.promotions.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    today = datetime.utcnow().date()

    is_active = payload.promotions.is_active
    if is_active is None:
        is_active = start_date.date() <= today <= end_date.date()

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    promotion_kw: dict = {
        "promo_code": payload.promotions.promo_code,
        "name": payload.promotions.name or payload.promotions.promo_code,
        "promo_type": payload.promotions.promo_type,
        "description": payload.promotions.description,
        "start_date": start_date,
        "end_date": end_date,
        "is_active": is_active,
        "created_by": created_by,
    }
    if payload.access_levels is not None:
        promotion_kw["access_levels"] = payload.access_levels
    promotion = Promotion(**promotion_kw)
    db.add(promotion)
    db.flush()

    # Only add promotion_products for products that exist; missing codes are already in warnings.
    # Duplicate product_code rows: process first occurrence only; skip repeats and report in warnings.
    seen_product_codes: set[str] = set()
    skipped_duplicate_rows: list[dict] = []
    for item in payload.promotion_products:
        code = (item.product_code or "").strip()
        if code not in products_map:
            continue
        if code in seen_product_codes:
            skipped_duplicate_rows.append(
                {
                    "product_code": code,
                    "selling_price": item.selling_price,
                }
            )
            continue
        seen_product_codes.add(code)
        product = products_map[code]
        promo_price = item.selling_price
        discount_amount = item.discount_amount
        discount_percent = item.discount_percent
        if promo_price is not None and product.list_price:
            list_price = float(product.list_price)
            promo_price_float = float(promo_price)
            discount_amount = list_price - promo_price_float
            discount_percent = (discount_amount / list_price * 100) if list_price > 0 else 0
        discount_percent = clamp_discount_percent_for_db(discount_percent)
        db.add(
            PromotionProduct(
                promotion_id=promotion.id,
                product_id=product.id,
                promo_selling_price=promo_price,
                discount_amount=discount_amount,
                discount_percent=discount_percent,
            )
            )

    if skipped_duplicate_rows:
        warnings.append(
            {
                "message": (
                    "Skipped duplicate product rows (only the first occurrence per product code was applied)."
                ),
                "skipped_duplicates": skipped_duplicate_rows,
            }
        )

    # Link attachments to the promotion if provided (root-level attachment_id or promotions.attachment_id list)
    attachment_ids = _attachment_ids_from_promotion_payload(payload)
    if attachment_ids:
        created_by_uuid = created_by
        found = db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()
        existing_attachment_ids = {a.id for a in found}
        missing = [aid for aid in attachment_ids if aid not in existing_attachment_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Attachment(s) not found", "attachment_ids": missing},
            )
        for sort_order, aid in enumerate(attachment_ids):
            db.add(
                PromotionAttachment(
                    promotion_id=promotion.id,
                    attachment_id=aid,
                    is_primary=(sort_order == 0),
                    sort_order=sort_order,
                    created_by=created_by_uuid,
                )
            )

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise_promotion_product_unique_violation(db, e)

    db.refresh(promotion)

    # Notify: attachment uploaders (if linked + uploaded_by) and/or notify_user_id (system API key has no created_by).
    try:
        notify_after_external_promotion_created(
            db,
            promotion,
            attachment_ids,
            payload.notify_user_id,
        )
    except Exception as e:
        logger.warning(
            "External promotion created but notification failed: %s",
            e,
            exc_info=True,
        )

    return PromotionCreateResponse(
        promotion=PromotionResponse.model_validate(promotion),
        already_existed=False,
        message=None,
        warnings=warnings,
    )
