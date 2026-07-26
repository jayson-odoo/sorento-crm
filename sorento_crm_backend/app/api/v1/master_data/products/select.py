"""Product select endpoint for dropdowns."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.models.product import Product
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select")
async def get_products_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get products for select/dropdown (simplified list)."""
    try:
        q = db.query(Product).filter(Product.is_active == True)
        
        if query:
            q = q.filter(
                (Product.product_code.ilike(f"%{query}%")) |
                (Product.product_name.ilike(f"%{query}%"))
            )
        
        products = q.limit(100).all()

        # Category, brand, list price and the discontinued flag are what a
        # product dropdown actually shows. Their absence was not cosmetic: a
        # picker with no `is_discontinued` offers a product nobody can buy with
        # nothing to say so. `invoice_price` and `cost_price` stay out - a
        # dropdown is not an entitlement check.
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
                    "is_discontinued": bool(p.is_discontinued),
                }
                for p in products
            ]
        }
    except Exception as e:
        raise handle_internal_error(str(e))
