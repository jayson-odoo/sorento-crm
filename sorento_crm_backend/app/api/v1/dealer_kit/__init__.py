"""Dealer Kit API routes.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.
"""
from fastapi import APIRouter

from app.api.v1.dealer_kit import (
    assets,
    catalogue,
    editions,
    flyer_readings,
    flyer_spec_proposals,
    pages,
    price_tag_requests,
    selections,
    tag_data,
    tag_templates,
)

router = APIRouter()
router.include_router(pages.router)
router.include_router(assets.router)
router.include_router(catalogue.router)
router.include_router(selections.router)
# BEFORE the readings router, and that order is load-bearing: `GET
# /flyer-readings/{reading_id}` would otherwise match
# `/flyer-readings/spec-proposal-batches` and answer 404 for a reading nobody
# named. FastAPI matches in declaration order, so the static path has to be
# registered first.
router.include_router(flyer_spec_proposals.router)
router.include_router(flyer_readings.router)
router.include_router(editions.router)
router.include_router(price_tag_requests.router)
router.include_router(tag_templates.router)
router.include_router(tag_data.router)
