"""Product select endpoint for dropdowns."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.models.product import Product
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select")
async def get_products_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get products for select dropdowns."""
    try:
        from sqlalchemy import or_
        q = db.query(Product).filter(Product.is_active == True)
        
        if query:
            q = q.filter(
                or_(
                    Product.product_code.ilike(f"%{query}%"),
                    Product.product_name.ilike(f"%{query}%")
                )
            )
        
        products = q.limit(100).all()
        return {
            "data": products,
            "pagination": {"total": len(products), "page": 1, "limit": len(products)},
            "empty": len(products) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))
