"""Marketing API routes."""
from fastapi import APIRouter
from app.api.v1.marketing import (
    promotions,
    promotion_products,
    promotion_attachments,
    promotion_types,
    campaigns,
    campaign_types,
)

router = APIRouter()

router.include_router(promotions.router, prefix="/promotions", tags=["promotions"])
# Standalone promotion products router for listing all promotion products
router.include_router(promotion_products.router, prefix="/promotion-products", tags=["promotion-products"])
router.include_router(promotion_attachments.router, prefix="/promotion-attachments", tags=["promotion-attachments"])
# The vocabulary behind per-type expiry behaviour (admin-maintained).
router.include_router(promotion_types.router, prefix="/promotion-types", tags=["promotion-types"])
router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
router.include_router(campaign_types.router, prefix="/campaign-types", tags=["campaign-types"])
