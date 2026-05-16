"""External API for promotions."""
import logging
import re
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.marketing import (
    PromotionGroupItem,
    PromotionRequest,
    PromotionCreateResponse,
)
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


def _product_code_candidates(raw_code: Optional[str]) -> list[str]:
    """
    Candidate product codes for matching.
    Priority: exact code as provided, then split by '+' parts (trimmed).
    """
    code = (raw_code or "").strip()
    if not code:
        return []
    out: list[str] = [code]
    parts = [p.strip() for p in re.split(r"\s*\+\s*", code) if p and p.strip()]
    for p in parts:
        if p not in out:
            out.append(p)
    return out


def _resolve_product_codes(raw_code: Optional[str], products_map: dict) -> list[str]:
    """
    Resolve payload product_code into concrete product codes:
    - exact match first
    - fallback to '+' split parts when exact doesn't exist
    """
    candidates = _product_code_candidates(raw_code)
    if not candidates:
        return []
    exact = candidates[0]
    if exact in products_map:
        return [exact]
    return [c for c in candidates[1:] if c in products_map]


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
                product_codes.extend(_product_code_candidates(row.product_code))
    else:
        product_codes = []
        for item in (payload.promotion_products or []):
            product_codes.extend(_product_code_candidates(item.product_code))
    products_map = get_products_by_code_exact(db, product_codes)
    if payload.promotion_groups:
        source_codes = [row.product_code for g in payload.promotion_groups for row in g.promotion_products]
    else:
        source_codes = [item.product_code for item in (payload.promotion_products or [])]
    missing_codes = [c for c in source_codes if not _resolve_product_codes(c, products_map)]
    # Missing product codes are a warning only: create the promotion and link only products that exist
    warnings = []
    if missing_codes:
        warnings.append(
            {
                "message": "Missing product codes (exact match, then '+' split fallback)",
                "product_codes": missing_codes,
            }
        )

    start_date = parse_date_value(payload.promotions.start_date)
    end_date = parse_date_value(payload.promotions.end_date)
    today = datetime.utcnow().date()

    is_active = payload.promotions.is_active
    if is_active is None:
        if start_date and end_date:
            is_active = start_date <= today <= end_date
        else:
            is_active = True

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    promotion_kw: dict = {
        "description": payload.promotions.description,
        "start_date": start_date,
        "end_date": end_date,
        "is_active": is_active,
        "created_by": created_by,
    }
    if payload.access_levels is not None:
        promotion_kw["access_levels"] = payload.access_levels

    # TCK-2026-000020: when n8n re-sends a promotion with the same description,
    # update the still-editable row in place (replace groups + products + links)
    # instead of duplicate-creating. "Locked" = end_date already passed.
    from sqlalchemy import func as _sa_func

    desc_norm = (payload.promotions.description or "").strip()
    existing_promotion = None
    if desc_norm:
        existing_promotion = (
            db.query(Promotion)
            .filter(_sa_func.lower(_sa_func.trim(Promotion.description)) == desc_norm.lower())
            .order_by(Promotion.created_at.desc())
            .first()
        )
    if existing_promotion is not None:
        # If the promotion's window has ended, reject — it's locked.
        if existing_promotion.end_date is not None and existing_promotion.end_date < today:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Promotion '{desc_norm}' already exists and is past end_date "
                    f"({existing_promotion.end_date}); cannot update."
                ),
            )
        for key, value in promotion_kw.items():
            if key == "created_by":
                continue
            if value is not None:
                setattr(existing_promotion, key, value)
        # Drop existing groups + lines so we can rebuild from the payload.
        for g in list(getattr(existing_promotion, "promotion_groups", []) or []):
            db.delete(g)
        for pa in list(getattr(existing_promotion, "promotion_attachments", []) or []):
            db.delete(pa)
        db.flush()
        promotion = existing_promotion
        already_existed_flag = True
    else:
        promotion = Promotion(**promotion_kw)
        db.add(promotion)
        db.flush()
        already_existed_flag = False

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
                resolved_codes = _resolve_product_codes(item.product_code, products_map)
                if not resolved_codes:
                    continue
                for code in resolved_codes:
                    if code in seen_in_group:
                        skipped_duplicate_rows.append(
                            {
                                "group": pg.group_name,
                                "product_code": code,
                                "source_product_code": (item.product_code or "").strip(),
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
            resolved_codes = _resolve_product_codes(item.product_code, products_map)
            if not resolved_codes:
                continue
            for code in resolved_codes:
                if code in seen_product_codes:
                    skipped_duplicate_rows.append(
                        {
                            "product_code": code,
                            "source_product_code": (item.product_code or "").strip(),
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
            warnings=missing_codes or None,
        )
    except Exception as e:
        logger.warning(
            "External promotion created but notification failed: %s",
            e,
            exc_info=True,
        )

    return PromotionCreateResponse(
        promotion=PromotionResponse.model_validate(promotion),
        already_existed=already_existed_flag,
        message=("Promotion updated in place." if already_existed_flag else None),
        warnings=warnings,
        unknown_product_codes=missing_codes,
    )
