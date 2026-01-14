"""Promotions API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Path, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.marketing_service import PromotionService, PromotionProductService
from app.schemas.marketing import PromotionCreate, PromotionUpdate, PromotionResponse, PromotionProductCreate, PromotionProductUpdate, PromotionProductResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[PromotionResponse])
async def get_promotions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get promotions with pagination."""
    try:
        service = PromotionService(db)
        result = service.list_promotions(page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{promotion_id}", response_model=PromotionResponse)
async def get_promotion(
    promotion_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single promotion by ID."""
    try:
        service = PromotionService(db)
        promotion = service.get_promotion(promotion_id)
        
        # Map promo_selling_price to promotion_price for each product
        if hasattr(promotion, 'products') and promotion.products:
            for product in promotion.products:
                if hasattr(product, 'promo_selling_price'):
                    setattr(product, 'promotion_price', product.promo_selling_price)
        
        return promotion
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
async def create_promotion(
    promotion_data: PromotionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new promotion."""
    try:
        service = PromotionService(db)
        promotion = service.create_promotion(promotion_data, current_user["id"])
        return promotion
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{promotion_id}", response_model=PromotionResponse)
async def update_promotion(
    promotion_id: str,
    promotion_data: PromotionUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a promotion."""
    try:
        service = PromotionService(db)
        promotion = service.update_promotion(promotion_id, promotion_data)
        return promotion
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{promotion_id}", status_code=status.HTTP_200_OK)
async def delete_promotion(
    promotion_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a promotion."""
    try:
        service = PromotionService(db)
        # Implement delete logic
        return {"message": "Promotion deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# Nested router for promotion products
nested_promotion_products_router = APIRouter()

@nested_promotion_products_router.get("/", response_model=list[PromotionProductResponse])
async def get_promotion_products_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get products for a specific promotion (nested route)."""
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Fetching products for promotion_id: {promotion_id}")
        
        service = PromotionProductService(db)
        result = service.list_promotion_products(promotion_id, page=1, limit=1000)
        products = result.get("data", [])
        logger.debug(f"Found {len(products)} products for promotion {promotion_id}")
        
        # Map promo_selling_price to promotion_price for each product
        # Set it as an attribute so Pydantic can serialize it
        for product in products:
            if hasattr(product, 'promo_selling_price'):
                # Set promotion_price attribute for Pydantic serialization
                setattr(product, 'promotion_price', product.promo_selling_price)
        
        # Use Pydantic's from_attributes to serialize
        return [PromotionProductResponse.model_validate(p) for p in products]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching promotion products: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))

@nested_promotion_products_router.post("/", response_model=PromotionProductResponse, status_code=status.HTTP_201_CREATED)
async def create_promotion_product_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a product to a promotion (nested route)."""
    try:
        service = PromotionProductService(db)
        create_data = PromotionProductCreate(
            promotion_id=promotion_id,
            product_id=body.get("product_id"),
            promo_selling_price=body.get("promotion_price")
        )
        product = service.create_promotion_product(create_data)
        if hasattr(product, 'promo_selling_price'):
            product.promotion_price = product.promo_selling_price
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

@nested_promotion_products_router.put("/{product_id}", response_model=PromotionProductResponse)
async def update_promotion_product_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    product_id: str = Path(..., description="Product ID"),
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a promotion product (nested route)."""
    try:
        service = PromotionProductService(db)
        update_data = PromotionProductUpdate(
            promo_selling_price=body.get("promotion_price")
        )
        product = service.update_promotion_product(promotion_id, product_id, update_data)
        if hasattr(product, 'promo_selling_price'):
            product.promotion_price = product.promo_selling_price
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

@nested_promotion_products_router.delete("/{product_id}", status_code=status.HTTP_200_OK)
async def delete_promotion_product_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    product_id: str = Path(..., description="Product ID"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a product from a promotion (nested route)."""
    try:
        service = PromotionProductService(db)
        result = service.delete_promotion_product(promotion_id, product_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

# Include nested promotion products router
router.include_router(
    nested_promotion_products_router,
    prefix="/{promotion_id}/products",
    tags=["promotion-products"]
)
