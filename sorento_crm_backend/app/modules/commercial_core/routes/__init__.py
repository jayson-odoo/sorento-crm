"""Commercial core API routes."""
from fastapi import APIRouter

from app.modules.commercial_core.routes import (
    entity_conversation,
    lead_respond_contacts,
    lead_stages,
    leads,
    pipeline,
    process_config,
    progression,
    projects,
    quotation_email_templates,
    quotation_workspace,
    respond_contacts_search,
    respond_workspace_picklist,
    tenders,
    workflow_stages,
)

# commercial_public_quoting lives in this package but is registered separately
# in app/api/v1/__init__.py without module guards (unauthenticated endpoint).

router = APIRouter()

router.include_router(leads.router, prefix="/leads", tags=["commercial-leads"])
router.include_router(lead_respond_contacts.router, prefix="/leads", tags=["commercial-lead-respond-contacts"])
router.include_router(respond_workspace_picklist.router, tags=["commercial-respond-workspaces"])
router.include_router(respond_contacts_search.router, tags=["commercial-respond-contacts"])
router.include_router(projects.router, prefix="/projects", tags=["commercial-projects"])
router.include_router(lead_stages.router, prefix="/lead-stages", tags=["commercial-lead-stages"])
router.include_router(workflow_stages.router, prefix="/workflow-stages", tags=["commercial-workflow-stages"])
router.include_router(process_config.router, prefix="/process-config", tags=["commercial-process-config"])
router.include_router(tenders.router, prefix="/tenders", tags=["commercial-tenders"])
router.include_router(progression.router, prefix="/tenders", tags=["commercial-progression"])
router.include_router(pipeline.router, prefix="/pipeline", tags=["commercial-pipeline"])
router.include_router(quotation_workspace.router, prefix="", tags=["commercial-quotation-workspace"])
router.include_router(quotation_email_templates.router, prefix="", tags=["commercial-quotation-email-templates"])
router.include_router(entity_conversation.router, prefix="", tags=["commercial-entity-conversation"])
