"""Warranty configuration routes (after-sales P2): policies, terms, kinds and kind rules."""
from fastapi import APIRouter

from app.api.v1.after_sales.warranty import kind_rules, kinds, policies, terms

router = APIRouter()
router.include_router(policies.router, prefix="/policies", tags=["warranty-policies"])
router.include_router(terms.router, prefix="/terms", tags=["warranty-terms"])
router.include_router(kinds.router, prefix="/kinds", tags=["warranty-kinds"])
router.include_router(kind_rules.router, prefix="/kind-rules", tags=["warranty-kind-rules"])
