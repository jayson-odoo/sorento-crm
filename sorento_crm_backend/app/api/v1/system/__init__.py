"""System-level API routes."""
from fastapi import APIRouter, Depends
from app.api.v1.system import (
    health,
    import_logs,
    jobs,
    calendar,
    outgoing_mails,
    scheduled_tasks,
    numbering_rules,
    embeddings,
    ai_assistant,
    references,
    tool_capabilities,
    mcp_tools,
    mcp_access,
    mcp_routing,
    respond_workspaces,
    email_templates,
    automation,
    email_outbox,
    email_event_configs,
    respond_outbox,
)
from app.modules.runtime.guards import require_module_enabled_with_api_key

router = APIRouter(dependencies=[Depends(require_module_enabled_with_api_key("base"))])

router.include_router(health.router, tags=["health"])
router.include_router(import_logs.router, tags=["import-logs"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(calendar.router, tags=["calendar"])
router.include_router(outgoing_mails.router, tags=["outgoing-mails"])
router.include_router(scheduled_tasks.router, tags=["scheduled-tasks"])
router.include_router(numbering_rules.router, tags=["numbering-rules"])
router.include_router(embeddings.router, tags=["embeddings"])
router.include_router(ai_assistant.router, tags=["ai-assistant"])
router.include_router(references.router, tags=["references"])
router.include_router(tool_capabilities.router, tags=["tool-capabilities"])
router.include_router(mcp_tools.router, tags=["mcp-tools"])
router.include_router(mcp_access.router, tags=["mcp-access"])
router.include_router(mcp_routing.router, tags=["mcp-routing"])
router.include_router(respond_workspaces.router, tags=["respond-workspaces"])
router.include_router(email_templates.router, tags=["email-templates"])
router.include_router(automation.router, tags=["automation"])
router.include_router(email_outbox.router, tags=["email-outbox"])
router.include_router(email_event_configs.router, tags=["email-event-configs"])
router.include_router(respond_outbox.router, tags=["respond-outbox"])
