"""Dealer Kit API routes.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.
"""
from fastapi import APIRouter

from app.api.v1.dealer_kit import catalogue, flyer_readings, pages, selections

router = APIRouter()
router.include_router(pages.router)
router.include_router(catalogue.router)
router.include_router(selections.router)
router.include_router(flyer_readings.router)
