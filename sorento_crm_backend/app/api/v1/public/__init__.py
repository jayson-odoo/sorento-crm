"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import ai_extract, approval, consent_notice, portal, ticket_drafts, view

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
router.include_router(view.router, prefix="/view", tags=["public-view"])
router.include_router(portal.router, prefix="/portal", tags=["public-portal"])
# A consumer must be able to read what they are agreeing to before identifying themselves.
router.include_router(consent_notice.router, tags=["public-consent-notice"])
router.include_router(ai_extract.router, prefix="/portal", tags=["public-portal-ai-extract"])
router.include_router(
    ticket_drafts.router, prefix="/ticket-drafts", tags=["public-ticket-drafts"]
)
