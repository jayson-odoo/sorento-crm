"""Promotion products API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.marketing_service import PromotionProductService, _resolve_promotion_id_for_filter
from app.schemas.marketing import PromotionProductCreate, PromotionProductUpdate, PromotionProductResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


# Standalone endpoint for listing all promotion products
@router.get("/", response_model=ListResponse[PromotionProductResponse])
async def list_all_promotion_products(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    query: Optional[str] = Query(
        None,
        description="Text search on product code, product name, and promotion promo_code (not promotion id).",
    ),
    promotion_id: Optional[str] = Query(
        None,
        description="Filter lines to one promotion: UUID or promo_code.",
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get promotion products with pagination. Scope to one promotion via promotion_id; use query for text search."""
    try:
        service = PromotionProductService(db)
        resolved_pid: Optional[str] = None
        if promotion_id is not None and str(promotion_id).strip():
            resolved_pid = _resolve_promotion_id_for_filter(db, promotion_id)
            if resolved_pid is None:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }

        result = service.list_promotion_products(
            promotion_id=resolved_pid,
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            query=query
        )
        # Map promo_selling_price to promotion_price for each product
        products = result.get("data", [])
        for product in products:
            if hasattr(product, 'promo_selling_price'):
                product.promotion_price = product.promo_selling_price
        result["data"] = products
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# Note: POST, PUT, DELETE endpoints for promotion products are handled in the nested router
# under /promotions/{promotion_id}/products in promotions.py
