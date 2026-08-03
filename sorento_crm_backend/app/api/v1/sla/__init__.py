"""SLA management API routes."""
from fastapi import APIRouter
from app.api.v1.sla import sla_policies, sla_tracking, form_sla_config, form_sla_tracking, form_skip, sla_kpi

router = APIRouter()

router.include_router(sla_policies.router, prefix="/sla-policies", tags=["sla-policies"])
router.include_router(sla_tracking.router, prefix="/conversation-sla-tracking", tags=["sla-tracking"])
router.include_router(form_sla_config.router, prefix="/form-sla-config", tags=["form-sla-config"])
router.include_router(form_sla_tracking.router, prefix="/form-sla-tracking", tags=["form-sla-tracking"])
router.include_router(form_skip.router, prefix="/form", tags=["form-skip"])
router.include_router(sla_kpi.router, prefix="/kpi", tags=["sla-kpi"])
# Event logs are part of sla_tracking router, accessible at /conversation-sla-tracking/event-logs