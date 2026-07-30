"""Product select endpoint for dropdowns."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.models.product import Product
from app.services.error_handler import handle_internal_error

router = APIRouter()

#: Kept at 100 because that is what this endpoint used to return unconditionally.
#: Callers that never pass a limit (SCM policy scopes, the variant picker) get
#: exactly what they got before; only a caller that asks for paging changes.
DEFAULT_LIMIT = 100


@router.get("/select")
async def get_products_select(
    query: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Products for a dropdown, SEARCHED AND PAGED ON THE SERVER.

    The paging is the point. This used to return the first 100 active rows with
    no way to ask for more, so a caller that filtered client-side could only
    ever see those 100 - and with 22,000 active products, a search for a code
    that exists 998 times answered "no products match". A dropdown that
    silently hides most of the catalogue is worse than a slow one.

    Ordered by code so paging is stable: without an ORDER BY, two pages of the
    same result set can repeat or skip rows.

    Fields are listed explicitly rather than dumping the ORM row. That is not
    tidiness - the raw row carried `cost_price` and `invoice_price`, and a
    dropdown is not the place to decide who may see a margin.
    """
    try:
        from sqlalchemy import or_
        q = db.query(Product).filter(Product.is_active == True)

        if query:
            needle = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Product.product_code.ilike(needle),
                    Product.product_name.ilike(needle)
                )
            )

        if category_id:
            # Narrowing by category is what turns a 22,000-product dropdown
            # into a browsable one. It composes with the search term rather
            # than replacing it: "basins, containing 800".
            q = q.filter(Product.category_id == category_id)

        products = q.order_by(Product.product_code).offset(offset).limit(limit).all()

        # Category, brand, list price and the discontinued flag are what a
        # product dropdown actually shows. `is_discontinued` in particular was
        # missing: a picker without it offers a product nobody can buy and has
        # nothing to say so.
        return {
            "data": [
                {
                    "id": p.id,
                    "product_code": p.product_code,
                    "product_name": p.product_name,
                    "category_name": (
                        p.category.category_name if p.category is not None else None
                    ),
                    "brand_name": p.brand.brand_name if p.brand is not None else None,
                    "list_price": str(p.list_price) if p.list_price is not None else None,
                    "currency": p.currency,
                    "is_discontinued": bool(p.is_discontinued),
                }
                for p in products
            ],
            # `total` is the size of THIS page, as it always has been. A true
            # count would be a second full scan on every keystroke, and no
            # caller reads it; the honest signal that more exists is a full page.
            "pagination": {
                "total": len(products),
                "page": (offset // limit) + 1,
                "limit": limit,
                "offset": offset,
            },
            "empty": len(products) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))
