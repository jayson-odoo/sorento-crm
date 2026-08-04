"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import ai_extract, approval, portal, quotation_sign, ticket_drafts, view

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
router.include_router(view.router, prefix="/view", tags=["public-view"])
router.include_router(portal.router, prefix="/portal", tags=["public-portal"])
router.include_router(
    quotation_sign.router, prefix="/quotation-sign", tags=["public-quotation-sign"]
)
router.include_router(ai_extract.router, prefix="/portal", tags=["public-portal-ai-extract"])
router.include_router(
    ticket_drafts.router, prefix="/ticket-drafts", tags=["public-ticket-drafts"]
)
