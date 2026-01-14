"""SLA management API routes."""
from fastapi import APIRouter
from app.api.v1.sla import sla_policies, sla_tracking

router = APIRouter()

router.include_router(sla_policies.router, prefix="/sla-policies", tags=["sla-policies"])
router.include_router(sla_tracking.router, prefix="/conversation-sla-tracking", tags=["sla-tracking"])
