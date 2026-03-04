"""External API routes."""
from fastapi import APIRouter
from app.api.v1.external import (
    packing_lists,
    spo_allocations,
    grn,
    product_attachments,
    promotions,
    forms,
    complaint_attachments,
    purchase_requests,
    next_assignee,
    conversation_assignee,
    presigned_url,
)

router = APIRouter()

router.include_router(packing_lists.router, prefix="/packing-lists", tags=["external"])
router.include_router(spo_allocations.router, prefix="/spo-allocations", tags=["external"])
router.include_router(grn.router, prefix="/grn", tags=["external"])
router.include_router(product_attachments.router, prefix="/product-attachments", tags=["external"])
router.include_router(promotions.router, prefix="/promotions", tags=["external"])
router.include_router(forms.router, prefix="/forms", tags=["external"])
router.include_router(complaint_attachments.router, prefix="/complaint-attachments", tags=["external"])
router.include_router(purchase_requests.router, prefix="/purchase-requests", tags=["external"])
router.include_router(next_assignee.router, prefix="/next-assignee", tags=["external"])
router.include_router(conversation_assignee.router, prefix="/conversation-assignee", tags=["external"])
router.include_router(presigned_url.router, prefix="/presigned-url", tags=["external"])
