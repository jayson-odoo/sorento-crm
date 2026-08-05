"""Product specifications: what was derived, and what the ranker does with it.

Two read surfaces, both for staff:

  * the derived specs per product, so a human can see what the machine read out of
    the catalog and which rows need attention.
  * a spec-search PREVIEW, so the ranker can be judged by someone who sells this
    catalog rather than by the person who wrote the weights.

The preview is the point. The relevance floor and the per-key weights are currently
one engineer's judgement measured against a small eval set; they only become right
when a product person types real phrases and says which results are wrong.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.product import Product, ProductCategory
from app.models.product_spec import ProductSpecException, ProductSpecifications
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.product_class_signal import explain_code
from app.services.product_spec_search import RELEVANCE_FLOOR, search_specs

router = APIRouter()

# `is_accessory` is derived and stored on every product for the ranker's deboost, but
# it is not a thing a customer states — it has no registry row (see
# product_spec_registry.py) and must not appear as a "spec" in either display surface.
_INTERNAL_ONLY_VALUE_KEYS = {"is_accessory"}


def _display_values(values: dict) -> dict:
    return {k: v for k, v in values.items() if k not in _INTERNAL_ONLY_VALUE_KEYS}


class SpecPreviewRequest(BaseModel):
    """A phrase as the ranker sees it, once the parser has done its half."""

    specs: list[dict] = Field(
        default_factory=list,
        description="[{key, value}] drawn from the Spec Registry.",
    )
    free_terms: list[str] = Field(
        default_factory=list,
        description="Words that did not map onto a registry key.",
    )
    include_accessories: bool = Field(
        default=False,
        description="Relax the accessory deboost. Never a filter.",
    )
    floor: Optional[float] = Field(
        default=None,
        description="Override the relevance floor, to see what it is currently hiding.",
    )


@router.get("/")
async def list_product_specifications(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None, description="Match a product code or class."),
    status: Optional[str] = Query(None, description="derived | needs_review | approved"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Derived specs, one row per product, newest derivation first."""
    try:
        q = (
            db.query(ProductSpecifications, Product, ProductCategory)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        )
        if query:
            wild = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Product.product_code.ilike(wild),
                    ProductCategory.class_label.ilike(wild),
                )
            )
        if status:
            q = q.filter(ProductSpecifications.status == status)

        total = q.count()
        rows = (
            q.order_by(Product.product_code)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        # One grouped count rather than a query per row: this list is the first thing
        # a reviewer opens, and an N+1 here is felt immediately.
        codes = [product.product_code for _, product, _ in rows]
        exception_counts = dict(
            db.query(ProductSpecException.product_code, func.count(ProductSpecException.id))
            .filter(
                ProductSpecException.product_code.in_(codes or [""]),
                ProductSpecException.resolved_at.is_(None),
            )
            .group_by(ProductSpecException.product_code)
            .all()
        )

        data = []
        for spec, product, category in rows:
            values = spec.values or {}
            data.append(
                {
                    "product_id": str(product.id),
                    "product_code": product.product_code,
                    "class_label": (values.get("class") or {}).get("value")
                    or (category.class_label if category else None),
                    "brand_hint": (values.get("brand") or {}).get("value"),
                    "spec_count": len(
                        [k for k in values if k not in ("class", "brand", "is_accessory")]
                    ),
                    "rendered_text": spec.rendered_text,
                    "status": spec.status,
                    "is_accessory": bool((values.get("is_accessory") or {}).get("value")),
                    "is_discontinued": bool(product.is_discontinued),
                    "open_exceptions": exception_counts.get(product.product_code, 0),
                    "values": _display_values(values),
                    "provenance": _display_values(spec.provenance or {}),
                }
            )

        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-product/{product_id}")
async def get_product_specification(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Everything derived for one product, plus WHY when nothing was.

    Opened from the product record itself, so it must answer the question actually
    being asked there — "is this product findable by description, and if not what is
    stopping it" — rather than only rendering whatever rows happen to exist. A product
    outside the enabled classes returns an empty spec and a reason, never a blank.
    """
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise handle_not_found("Product", product_id)

        category = (
            db.query(ProductCategory).filter(ProductCategory.id == product.category_id).first()
            if product.category_id
            else None
        )
        spec = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id == product.id)
            .first()
        )
        exceptions = (
            db.query(ProductSpecException)
            .filter(
                ProductSpecException.product_code == product.product_code,
                ProductSpecException.resolved_at.is_(None),
            )
            .order_by(ProductSpecException.spec_key)
            .all()
        )

        diagnosis = explain_code(category.category_code if category else None)
        # "Eligible" only describes the category. A product whose class IS enabled but
        # which still has no row means the derivation job has not covered it yet — a
        # different problem with a different fix, so it gets its own reason.
        if spec is None and diagnosis["reason"] == "eligible":
            diagnosis = {**diagnosis, "reason": "not_yet_derived"}

        return {
            "product_id": str(product.id),
            "product_code": product.product_code,
            "category_code": category.category_code if category else None,
            "searchable": bool(spec),
            "diagnosis": diagnosis,
            "spec": (
                {
                    "values": _display_values(spec.values or {}),
                    "provenance": _display_values(spec.provenance or {}),
                    "rendered_text": spec.rendered_text,
                    "status": spec.status,
                    "derived_at": (spec.updated_at or spec.created_at).isoformat(),
                }
                if spec
                else None
            ),
            "exceptions": [
                {
                    "id": str(row.id),
                    "spec_key": row.spec_key,
                    "reason": row.reason,
                    "proposed": row.proposed,
                    "stored": row.stored,
                }
                for row in exceptions
            ],
            "source_text": product.description or product.product_name or "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/exceptions")
async def list_spec_exceptions(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Open exceptions only. If routine successes ever appear here, the filter is wrong."""
    try:
        q = db.query(ProductSpecException).filter(ProductSpecException.resolved_at.is_(None))
        total = q.count()
        rows = (
            q.order_by(ProductSpecException.product_code)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "product_code": row.product_code,
                    "spec_key": row.spec_key,
                    "reason": row.reason,
                    "proposed": row.proposed,
                    "stored": row.stored,
                }
                for row in rows
            ],
            "pagination": {"total": total, "page": page, "limit": limit},
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/preview-search")
async def preview_spec_search(
    payload: SpecPreviewRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the ranker exactly as the chatbot would, and show its working.

    Returns the score and the matched keys per candidate so a reviewer can see WHY a
    result placed where it did, rather than only that it did.
    """
    try:
        result = search_specs(
            db,
            specs=payload.specs,
            free_terms=payload.free_terms,
            include_accessories=payload.include_accessories,
            floor=payload.floor if payload.floor is not None else RELEVANCE_FLOOR,
        )
        return {
            "candidates": result["candidates"],
            "floor_missed": result["floor_missed"],
            "top_score": result["top_score"],
            "floor": payload.floor if payload.floor is not None else RELEVANCE_FLOOR,
        }
    except Exception as e:
        raise handle_internal_error(str(e))
