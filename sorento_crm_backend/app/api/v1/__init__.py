"""API v1 routes."""
from fastapi import APIRouter, Depends
from app.api.v1 import (
    auth,
    audit,
    master_data,
    order_management,
    inventory,
    procurement,
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
)
from app.api.v1.system import modules_runtime
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
    dependencies=[Depends(require_module_enabled("product"))],
)
api_router.include_router(
    order_management.router,
    prefix="/order-management",
    tags=["order-management"],
    dependencies=[Depends(require_module_enabled("order"))],
)
api_router.include_router(
    inventory.router,
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(require_module_enabled("inventory"))],
)
api_router.include_router(
    procurement.router,
    prefix="/procurement",
    tags=["procurement"],
    dependencies=[Depends(require_module_enabled("procurement"))],
)
api_router.include_router(
    marketing.router,
    prefix="/marketing",
    tags=["marketing"],
    dependencies=[Depends(require_module_enabled("marketing"))],
)
api_router.include_router(
    forms.router,
    prefix="/forms-management",
    tags=["forms"],
    dependencies=[Depends(require_module_enabled("forms"))],
)
api_router.include_router(
    complaints.router,
    prefix="/complaints-management",
    tags=["complaints"],
    dependencies=[Depends(require_module_enabled("complaints"))],
)
api_router.include_router(
    sla.router,
    prefix="/sla-management",
    tags=["sla"],
    dependencies=[Depends(require_module_enabled("sla"))],
)
api_router.include_router(
    resources.router,
    prefix="/resource-management",
    tags=["resources"],
    dependencies=[Depends(require_module_enabled("resources"))],
)
api_router.include_router(
    user_management.router,
    prefix="/user-management",
    tags=["user-management"],
    dependencies=[Depends(require_module_enabled("base"))],
)
api_router.include_router(
    integrations.logs.router,
    prefix="/integrations/logs",
    tags=["integrations"],
    dependencies=[Depends(require_module_enabled("base"))],
)
# Alias so /api/v1/integration-management/integration-logs/* works when requests hit backend directly (e.g. nginx)
api_router.include_router(
    integrations.logs.router,
    prefix="/integration-management/integration-logs",
    tags=["integrations"],
    dependencies=[Depends(require_module_enabled("base"))],
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