"""Promotion products API routes."""
import re
import uuid

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.marketing_service import PromotionProductService, _resolve_promotion_id_for_filter
from app.schemas.marketing import PromotionProductCreate, PromotionProductUpdate, PromotionProductResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()

# Mistaken MCP usage: query="promotion_id='<uuid>'" or query="<uuid>" — treat as promotion filter when promotion_id is omitted.
_PROMOTION_ID_ASSIGN_RE = re.compile(
    r"^\s*promotion_id\s*=\s*(?:'|\")?([0-9a-fA-F-]{36})(?:'|\")?\s*$",
    re.IGNORECASE,
)


def _implicit_promotion_and_text_query(q: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """If *q* is a bare UUID or looks like promotion_id=<uuid>, return (uuid_str, None); else (None, q) for text search."""
    if q is None:
        return None, None
    s = str(q).strip()
    if not s:
        return None, None
    m = _PROMOTION_ID_ASSIGN_RE.match(s)
    if m:
        return m.group(1), None
    try:
        return str(uuid.UUID(s)), None
    except ValueError:
        return None, q


def _comma_separated_promotion_uuids(q: Optional[str]) -> Optional[List[str]]:
    """If *q* is 'uuid,uuid,...' (each segment a valid UUID), return normalized id strings; else None."""
    if q is None:
        return None
    s = str(q).strip()
    if not s or "," not in s:
        return None
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) < 2:
        return None
    out: List[str] = []
    for p in parts:
        try:
            out.append(str(uuid.UUID(p)))
        except ValueError:
            return None
    # stable dedupe
    return list(dict.fromkeys(out))


# Standalone endpoint for listing all promotion products
@router.get("/", response_model=ListResponse[PromotionProductResponse])
async def list_all_promotion_products(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    query: Optional[str] = Query(
        None,
        description="Prefer promotion_id for one promotion. Text search, or (if promotion_id omitted) one UUID / promotion_id='<uuid>' / comma-separated UUIDs for multiple promotions.",
    ),
    promotion_id: Optional[str] = Query(
        None,
        description="Single promotion: UUID or promo_code (preferred over encoding ids in query).",
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get promotion products with pagination. Scope to one promotion via promotion_id; use query for text search."""
    try:
        service = PromotionProductService(db)
        resolved_pid: Optional[str] = None
        resolved_pids: Optional[List[str]] = None
        text_query = query

        if promotion_id is not None and str(promotion_id).strip():
            resolved_pid = _resolve_promotion_id_for_filter(db, promotion_id)
            if resolved_pid is None:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
        else:
            multi = _comma_separated_promotion_uuids(query)
            if multi is not None:
                resolved_pids = []
                for uid in multi:
                    r = _resolve_promotion_id_for_filter(db, uid)
                    if r is None:
                        return {
                            "data": [],
                            "pagination": {"total": 0, "page": page, "limit": limit},
                            "empty": True,
                        }
                    resolved_pids.append(r)
                resolved_pids = list(dict.fromkeys(resolved_pids))
                text_query = None
            else:
                implicit_id, text_query = _implicit_promotion_and_text_query(query)
                if implicit_id:
                    resolved_pid = _resolve_promotion_id_for_filter(db, implicit_id)
                    if resolved_pid is None:
                        return {
                            "data": [],
                            "pagination": {"total": 0, "page": page, "limit": limit},
                            "empty": True,
                        }

        result = service.list_promotion_products(
            promotion_id=resolved_pid,
            promotion_ids=resolved_pids,
            page=page,
            limit=limit,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
            query=text_query
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
