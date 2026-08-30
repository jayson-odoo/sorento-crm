"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import (
    ai_extract,
    approval,
    catalogue,
    geo,
    onboarding,
    portal,
    portal_price_tag,
    print as print_route,
    quotation_sign,
    ticket_drafts,
    view,
)

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
router.include_router(view.router, prefix="/view", tags=["public-view"])
# BEFORE portal.router, and that ordering is the fix, not a preference (D49).
# Both are mounted at /portal and Starlette serves the FIRST route whose path
# matches. portal.py declares POST/PUT/GET/DELETE `/submissions/{kind}...`, and
# `price_tag_request` is in SUPPORTED_TYPES, so every price tag write was being
# answered by the generic handler: a 422 about `body.fields`, a key belonging to
# another form's schema, which is what the salesperson saw when Submit "did
# nothing". This router declares only literal price tag paths, so going first
# captures exactly the requests meant for it and leaves the legacy kinds alone.
router.include_router(
    portal_price_tag.router, prefix="/portal", tags=["public-portal-price-tag"]
)
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
# Render payload for the PDF worker: /api/v1/public/print/{download_id}?token=
router.include_router(print_route.router, prefix="/print", tags=["public-print"])
