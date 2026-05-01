"""API v1 routes."""
from fastapi import APIRouter, Depends
from app.api.v1 import (
    auth,
    audit,
    master_data,
    order_management,
    inventory,
    procurement,
    incoming_stock,
    marketing,
    forms,
    complaints,
    sla,
    resources,
    user_management,
    integrations,
    test_auth,
    system,
    external,
    public,
    notifications,
    list_query,
    workflow_forms,
    lookup,
)
from app.api.v1.system import modules_runtime
from app.api.v1.user_management.access_agent_mcp_tools import router as _agent_mcp_tools_router
from app.modules.runtime.guards import require_module_enabled, require_module_enabled_with_api_key

api_router = APIRouter()

# Include all module routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Auth endpoints: /login, /signup, /reset-password, /change-password, /verify-email
# App Store / module lifecycle (not behind base system router guard; uses its own permissions)
api_router.include_router(modules_runtime.router, prefix="/system/modules", tags=["system-modules"])
api_router.include_router(
    audit.router,
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_module_enabled_with_api_key("audit"))],
)
api_router.include_router(
    master_data.router,
    prefix="/master-data",
    tags=["master-data"],
    dependencies=[Depends(require_module_enabled_with_api_key("product"))],
)
api_router.include_router(
    order_management.router,
    prefix="/order-management",
    tags=["order-management"],
    dependencies=[Depends(require_module_enabled_with_api_key("order"))],
)
api_router.include_router(
    inventory.router,
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(require_module_enabled_with_api_key("inventory"))],
)
api_router.include_router(
    procurement.router,
    prefix="/procurement",
    tags=["procurement"],
    dependencies=[Depends(require_module_enabled_with_api_key("procurement"))],
)
# User-facing incoming-stock surface (redacts received quantities, hides IDs/SPO details).
# Intended primary route for the AI assistant / MCP layer.
api_router.include_router(
    incoming_stock.router,
    prefix="/incoming-stock",
    tags=["incoming-stock"],
    dependencies=[Depends(require_module_enabled_with_api_key("procurement"))],
)
api_router.include_router(
    marketing.router,
    prefix="/marketing",
    tags=["marketing"],
    dependencies=[Depends(require_module_enabled_with_api_key("marketing"))],
)
api_router.include_router(
    forms.router,
    prefix="/forms-management",
    tags=["forms"],
    dependencies=[Depends(require_module_enabled_with_api_key("forms"))],
)
api_router.include_router(
    workflow_forms.router,
    prefix="/workflow-forms",
    tags=["workflow-forms"],
    dependencies=[Depends(require_module_enabled_with_api_key("workflow_forms"))],
)
api_router.include_router(
    complaints.router,
    prefix="/complaints-management",
    tags=["complaints"],
    dependencies=[Depends(require_module_enabled_with_api_key("complaints"))],
)
api_router.include_router(
    sla.router,
    prefix="/sla-management",
    tags=["sla"],
    # JWT or X-API-Key (same EXTERNAL_API_KEY as /external/*) for n8n / automation
    dependencies=[Depends(require_module_enabled_with_api_key("sla"))],
)
api_router.include_router(
    resources.router,
    prefix="/resource-management",
    tags=["resources"],
    dependencies=[Depends(require_module_enabled_with_api_key("resources"))],
)
api_router.include_router(
    user_management.router,
    prefix="/user-management",
    tags=["user-management"],
    dependencies=[Depends(require_module_enabled("base"))],
)
# Per-agent MCP tool ownership sub-routes — mounted separately with API-key guard
# so automated callers (n8n, admin scripts) can use X-API-Key.
api_router.include_router(
    _agent_mcp_tools_router,
    prefix="/user-management/access-agents",
    tags=["access-agents"],
    dependencies=[Depends(require_module_enabled_with_api_key("base"))],
)
api_router.include_router(
    integrations.logs.router,
    prefix="/integrations/logs",
    tags=["integrations"],
    # JWT or X-API-Key so n8n / external tools can call logs (same key as /external/*)
    dependencies=[Depends(require_module_enabled_with_api_key("base"))],
)
# Alias so /api/v1/integration-management/integration-logs/* works when requests hit backend directly (e.g. nginx)
api_router.include_router(
    integrations.logs.router,
    prefix="/integration-management/integration-logs",
    tags=["integrations"],
    dependencies=[Depends(require_module_enabled_with_api_key("base"))],
)
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(test_auth.router, tags=["test"])
api_router.include_router(external.router, prefix="/external", tags=["external"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_module_enabled("notifications"))],
)
api_router.include_router(
    list_query.router,
    prefix="/list-query",
    tags=["list-query"],
)
api_router.include_router(lookup.router, prefix="/lookup", tags=["lookup"])

# Public quoting customer-approval endpoint — unauthenticated, must be mounted
# OUTSIDE the commercial_core module guard.
try:
    from app.modules.commercial_core.routes import commercial_public_quoting as _public_quoting
    api_router.include_router(
        _public_quoting.router,
        prefix="/public/commercial",
        tags=["commercial-public-quoting"],
    )
except Exception:  # noqa: BLE001
    # commercial_core not installed yet — skip silently.
    pass

# Auto-discovery of self-contained modules under app/modules/<key>/.
# Additive: skips prefixes already registered above (LEGACY_REGISTERED_PREFIXES).
from app.modules.runtime.discovery import discover_module_routers  # noqa: E402
discover_module_routers(api_router)