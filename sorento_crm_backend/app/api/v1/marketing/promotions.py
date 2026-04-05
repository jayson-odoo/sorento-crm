"""Promotions API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Path, Body
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.marketing_service import PromotionService, PromotionProductService
from app.schemas.marketing import (
    PromotionCreate,
    PromotionUpdate,
    PromotionResponse,
    PromotionListItemResponse,
    PromotionGroupCreate,
    PromotionGroupUpdate,
    PromotionGroupResponse,
    PromotionProductCreate,
    PromotionProductUpdate,
    PromotionProductResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


class BulkDeletePromotionsRequest(BaseModel):
    ids: list[str]


class BulkUpdateAccessLevelsRequest(BaseModel):
    ids: list[str]
    access_levels: list[str]


@router.get("/", response_model=ListResponse[PromotionListItemResponse])
async def get_promotions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None, description="Filter by access level: dealer, end_user"),
    status: Optional[str] = Query(None, description="Filter by status: active, inactive, all"),
    promo_type: Optional[str] = Query(None, description="Filter by promotion type e.g. price_override"),
    sort: Optional[str] = Query(None, description="Sort field e.g. created_at, promo_code, products_count"),
    dir: Optional[str] = Query("desc", description="asc or desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get promotions with pagination. Search and filter by status, access level, type."""
    try:
        service = PromotionService(db)
        result = service.list_promotions(
            page=page,
            limit=limit,
            user_type=user_type,
            query=query,
            status=status,
            promo_type=promo_type,
            sort_field=sort,
            sort_dir=dir,
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{promotion_id}", response_model=PromotionResponse)
async def get_promotion(
    promotion_id: str,
    user_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single promotion by ID."""
    try:
        service = PromotionService(db)
        promotion = service.get_promotion(promotion_id)
        if user_type and promotion.access_levels and user_type not in promotion.access_levels:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Promotion", promotion_id)
        
        # Map promo_selling_price to promotion_price for each line (flat list and nested groups)
        def _hydrate_promotion_price(pp):
            if hasattr(pp, "promo_selling_price"):
                setattr(pp, "promotion_price", pp.promo_selling_price)

        if hasattr(promotion, "products") and promotion.products:
            for product in promotion.products:
                _hydrate_promotion_price(product)
        if hasattr(promotion, "promotion_groups") and promotion.promotion_groups:
            for grp in promotion.promotion_groups:
                for pp in grp.promotion_products or []:
                    _hydrate_promotion_price(pp)

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


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_promotions(
    body: BulkDeletePromotionsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete promotions by ID."""
    try:
        service = PromotionService(db)
        return service.bulk_delete_promotions(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/bulk", status_code=status.HTTP_200_OK)
async def bulk_update_access_levels(
    body: BulkUpdateAccessLevelsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk set access levels for selected promotions."""
    try:
        service = PromotionService(db)
        return service.bulk_update_access_levels(body.ids, body.access_levels)
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
        service.delete_promotion(promotion_id)
        return {"message": "Promotion deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# Nested router: promotion groups (bundle / FOC)
nested_promotion_groups_router = APIRouter()


@nested_promotion_groups_router.post("/", response_model=PromotionGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_promotion_group_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    body: PromotionGroupCreate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a promotion group (e.g. bundle FOC rule)."""
    try:
        service = PromotionService(db)
        g = service.create_promotion_group(promotion_id, body)
        return PromotionGroupResponse.model_validate(g)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@nested_promotion_groups_router.put("/{group_id}", response_model=PromotionGroupResponse)
async def update_promotion_group_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    group_id: str = Path(..., description="Promotion group ID"),
    body: PromotionGroupUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a promotion group name, sort order, or FOC fields."""
    try:
        service = PromotionService(db)
        g = service.update_promotion_group(promotion_id, group_id, body)
        return PromotionGroupResponse.model_validate(g)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@nested_promotion_groups_router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_promotion_group_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    group_id: str = Path(..., description="Promotion group ID"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a promotion group (removes all product lines in that group). Cannot delete the last group."""
    try:
        service = PromotionService(db)
        return service.delete_promotion_group(promotion_id, group_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# Nested router for promotion products
nested_promotion_products_router = APIRouter()

@nested_promotion_products_router.get("/", response_model=list[PromotionProductResponse])
async def get_promotion_products_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    current_user: dict = Depends(get_current_user_or_api_key),
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
            promo_selling_price=body.get("promotion_price"),
            promotion_group_id=body.get("promotion_group_id"),
            dealer_discount_percent=body.get("dealer_discount_percent"),
        )
        product = service.create_promotion_product(create_data)
        if hasattr(product, 'promo_selling_price'):
            product.promotion_price = product.promo_selling_price
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

@nested_promotion_products_router.put("/{line_id}", response_model=PromotionProductResponse)
async def update_promotion_product_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    line_id: str = Path(..., description="Promotion product line id (promotion_products.id)"),
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a promotion product line (nested route). line_id is the junction row id (same SKU may appear in multiple groups)."""
    try:
        service = PromotionProductService(db)
        patch: dict = {}
        if "promotion_price" in body:
            patch["promo_selling_price"] = body["promotion_price"]
        if "dealer_discount_percent" in body:
            patch["dealer_discount_percent"] = body["dealer_discount_percent"]
        if "list_price" in body:
            patch["list_price"] = body["list_price"]
        if not patch:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")
        update_data = PromotionProductUpdate(**patch)
        product = service.update_promotion_product(promotion_id, line_id, update_data)
        if hasattr(product, 'promo_selling_price'):
            product.promotion_price = product.promo_selling_price
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

@nested_promotion_products_router.delete("/{line_id}", status_code=status.HTTP_200_OK)
async def delete_promotion_product_nested(
    promotion_id: str = Path(..., description="Promotion ID"),
    line_id: str = Path(..., description="Promotion product line id (promotion_products.id)"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a promotion product line (nested route)."""
    try:
        service = PromotionProductService(db)
        result = service.delete_promotion_product(promotion_id, line_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

router.include_router(
    nested_promotion_groups_router,
    prefix="/{promotion_id}/groups",
    tags=["promotion-groups"],
)

# Include nested promotion products router
router.include_router(
    nested_promotion_products_router,
    prefix="/{promotion_id}/products",
    tags=["promotion-products"]
)
