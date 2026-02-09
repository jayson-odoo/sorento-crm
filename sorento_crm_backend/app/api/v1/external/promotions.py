"""External API for promotions."""
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PromotionRequest, PromotionCreateResponse
from app.schemas.marketing import PromotionResponse
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.resources import Attachment
from app.api.v1.external.utils import parse_date_value, get_products_by_code_exact

router = APIRouter()


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
    """
    if not payload.promotion_products:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No promotion products provided")

    product_codes = [item.product_code for item in payload.promotion_products]
    products_map = get_products_by_code_exact(db, product_codes)
    missing_codes = [c for c in product_codes if (c or "").strip() not in products_map]
    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Missing product codes (exact match)", "product_codes": missing_codes},
        )

    existing = db.query(Promotion).filter(Promotion.promo_code == payload.promotions.promo_code).first()
    if existing:
        db.refresh(existing)
        return PromotionCreateResponse(
            promotion=PromotionResponse.model_validate(existing),
            already_existed=True,
            message="Promo code already exists.",
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
    promotion = Promotion(
        promo_code=payload.promotions.promo_code,
        name=payload.promotions.name or payload.promotions.promo_code,
        promo_type=payload.promotions.promo_type,
        description=payload.promotions.description,
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
        created_by=created_by,
    )
    db.add(promotion)
    db.flush()

    for item in payload.promotion_products:
        product = products_map[(item.product_code or "").strip()]
        promo_price = item.selling_price
        discount_amount = item.discount_amount
        discount_percent = item.discount_percent
        if promo_price is not None and product.list_price:
            list_price = float(product.list_price)
            promo_price_float = float(promo_price)
            discount_amount = list_price - promo_price_float
            discount_percent = (discount_amount / list_price * 100) if list_price > 0 else 0
        db.add(
            PromotionProduct(
                promotion_id=promotion.id,
                product_id=product.id,
                promo_selling_price=promo_price,
                discount_amount=discount_amount,
                discount_percent=discount_percent,
            )
        )

    # Link attachments to the promotion if provided
    attachment_ids = payload.promotions.attachment_id or []
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

    db.commit()
    db.refresh(promotion)
    return PromotionCreateResponse(
        promotion=PromotionResponse.model_validate(promotion),
        already_existed=False,
        message=None,
    )
