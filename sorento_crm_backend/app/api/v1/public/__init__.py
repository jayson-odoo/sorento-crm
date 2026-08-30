"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import (
    ai_extract,
    approval,
    branding,
    catalogue,
    geo,
    onboarding,
    portal,
    print as print_route,
    quotation_sign,
    supplier_request,
    ticket_drafts,
    view,
)

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
router.include_router(view.router, prefix="/view", tags=["public-view"])
router.include_router(portal.router, prefix="/portal", tags=["public-portal"])
router.include_router(
    quotation_sign.router, prefix="/quotation-sign", tags=["public-quotation-sign"]
)
# Onboarding intake, gated by the per-request token: /api/v1/public/onboarding/*
router.include_router(
    onboarding.router, prefix="/onboarding", tags=["public-onboarding"]
)
router.include_router(ai_extract.router, prefix="/portal", tags=["public-portal-ai-extract"])
router.include_router(
    ticket_drafts.router, prefix="/ticket-drafts", tags=["public-ticket-drafts"]
)
# The signature pad asks this while a customer is still signing, so it has to be reachable
# without a session exactly like the counter-sign page above it.
router.include_router(geo.router, prefix="/geo", tags=["public-geo"])
# Published catalogue pages: /api/v1/public/c/{company_code}/{slug}
router.include_router(catalogue.router, prefix="/c", tags=["public-catalogue"])
# The supplier's own view of a container request: /api/v1/public/supplier-request/{token}
router.include_router(
    supplier_request.router, prefix="/supplier-request", tags=["public-supplier-request"]
)
# The sign-in page's background, asked for before anyone has a session:
# /api/v1/public/branding
router.include_router(branding.router, prefix="/branding", tags=["public-branding"])
# Render payload for the PDF worker: /api/v1/public/print/{download_id}?token=
router.include_router(print_route.router, prefix="/print", tags=["public-print"])
