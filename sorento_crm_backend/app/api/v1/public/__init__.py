"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import approval, view_request, view_complaint, view_stock_inquiry

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
router.include_router(view_request.router, prefix="/view", tags=["public-view"])
router.include_router(view_complaint.router, prefix="/view", tags=["public-view"])
router.include_router(view_stock_inquiry.router, prefix="/view", tags=["public-view"])
