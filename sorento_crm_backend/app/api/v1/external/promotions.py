"""External API for promotions."""
import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import PromotionGroupItem, PromotionRequest, PromotionCreateResponse
from app.schemas.marketing import PromotionResponse
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct, PromotionAttachment
from app.models.resources import Attachment
from app.api.v1.external.utils import parse_date_value, get_products_by_code_exact
from app.services.marketing_service import (
    clamp_discount_percent_for_db,
    dealer_cost_and_margin_from_list,
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


def _foc_tiers_from_external_group(grp: PromotionGroupItem) -> Optional[list]:
    """
    Build promotion_groups.foc_tiers JSON.

    Priority: foc_rules (integration payload) → foc_tiers (CRM-style keys).
    """
    if grp.foc_rules:
        return [
            {"purchase_quantity": int(r.purchase_quantity_for_foc), "foc_quantity": int(r.foc_quantity)}
            for r in grp.foc_rules
        ]
    if grp.foc_tiers:
        return [
            {"purchase_quantity": int(t.purchase_quantity), "foc_quantity": int(t.foc_quantity)}
            for t in grp.foc_tiers
        ]
    return None


def _promotion_product_values(product, selling_price, discount_amount, discount_percent, dealer_discount):
    """List vs selling discount + optional dealer_discount (fraction off list for dealer cost)."""
    lp = float(product.list_price) if product.list_price else None
    promo_price = selling_price
    da = discount_amount
    dp = discount_percent
    # Same as legacy flat path: derive discount from list vs selling when both exist
    if promo_price is not None and lp is not None:
        da = lp - float(promo_price)
        dp = (da / lp * 100) if lp > 0 else 0
    dp = clamp_discount_percent_for_db(dp)
    dd = dealer_discount
    dc, margin = dealer_cost_and_margin_from_list(lp, float(dd) if dd is not None else None)
    return {
        "promo_selling_price": promo_price,
        "discount_amount": da,
        "discount_percent": dp,
        "dealer_discount_percent": dd,
        "dealer_cost": dc,
        "list_to_dealer_margin_amount": margin,
    }


@router.post("/", response_model=PromotionCreateResponse)
def create_promotion(
    payload: PromotionRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create a promotion linked to products. Use either:
    - `promotion_products` (flat list), or
    - `promotion_groups` (bundle / FOC groups with nested products; same SKU may appear in multiple groups).

    Products are matched by exact product_code (trim only, no case change).
    Optional `dealer_discount` per line (0.37 = 37% off list) stores dealer_cost and list-to-dealer margin.
    Per group you may set `dealer_discount` as default for all lines; line `dealer_discount` overrides.

    FOC tiers per group (optional; one of):
    - `foc_rules`: `[{ "purchase_quantity_for_foc", "foc_quantity" }, ...]` (integration shape), or
    - `foc_tiers`: `[{ "purchase_quantity", "foc_quantity" }, ...]`.

    Notifications (in-app + email): same as before for attachments + notify_user_id.
    """
    if payload.promotion_groups:
        product_codes = []
        for g in payload.promotion_groups:
            for row in g.promotion_products:
                product_codes.append(row.product_code)
    else:
        product_codes = [item.product_code for item in (payload.promotion_products or [])]
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

    skipped_duplicate_rows: list[dict] = []

    if payload.promotion_groups:
        for gi, grp in enumerate(payload.promotion_groups):
            foc_tiers_json = _foc_tiers_from_external_group(grp)
            group_dealer_discount = grp.dealer_discount
            pg = PromotionGroup(
                promotion_id=promotion.id,
                group_name=(grp.group_name or "").strip() or f"Group {gi + 1}",
                sort_order=gi,
                foc_tiers=foc_tiers_json,
            )
            db.add(pg)
            db.flush()
            seen_in_group: set[str] = set()
            for item in grp.promotion_products:
                code = (item.product_code or "").strip()
                if code not in products_map:
                    continue
                if code in seen_in_group:
                    skipped_duplicate_rows.append(
                        {
                            "group": pg.group_name,
                            "product_code": code,
                            "selling_price": item.selling_price,
                        }
                    )
                    continue
                seen_in_group.add(code)
                product = products_map[code]
                line_dealer_discount = (
                    item.dealer_discount if item.dealer_discount is not None else group_dealer_discount
                )
                vals = _promotion_product_values(
                    product,
                    item.selling_price,
                    item.discount_amount,
                    item.discount_percent,
                    line_dealer_discount,
                )
                db.add(
                    PromotionProduct(
                        promotion_id=promotion.id,
                        promotion_group_id=pg.id,
                        product_id=product.id,
                        **vals,
                    )
                )
    else:
        default_group = PromotionGroup(
            promotion_id=promotion.id,
            group_name="Default",
            sort_order=0,
            foc_tiers=None,
        )
        db.add(default_group)
        db.flush()
        seen_product_codes: set[str] = set()
        for item in payload.promotion_products or []:
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
            vals = _promotion_product_values(
                product,
                item.selling_price,
                item.discount_amount,
                item.discount_percent,
                item.dealer_discount,
            )
            db.add(
                PromotionProduct(
                    promotion_id=promotion.id,
                    promotion_group_id=default_group.id,
                    product_id=product.id,
                    **vals,
                )
            )

    if skipped_duplicate_rows:
        warnings.append(
            {
                "message": (
                    "Skipped duplicate product rows within the same group (first occurrence kept)."
                    if payload.promotion_groups
                    else "Skipped duplicate product rows (only the first occurrence per product code was applied)."
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
