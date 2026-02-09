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
    """Get products for select/dropdown (simplified list)."""
    try:
        q = db.query(Product).filter(Product.is_active == True)
        
        if query:
            q = q.filter(
                (Product.product_code.ilike(f"%{query}%")) |
                (Product.product_name.ilike(f"%{query}%"))
            )
        
        products = q.limit(100).all()
        
        return {
            "data": [
                {
                    "id": p.id,
                    "product_code": p.product_code,
                    "product_name": p.product_name,
                }
                for p in products
            ]
        }
    except Exception as e:
        raise handle_internal_error(str(e))
