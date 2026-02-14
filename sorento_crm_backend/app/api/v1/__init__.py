"""API v1 routes."""
from fastapi import APIRouter
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
)

api_router = APIRouter()

# Include all module routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Auth endpoints: /login, /signup, /reset-password, /change-password, /verify-email
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(master_data.router, prefix="/master-data", tags=["master-data"])
api_router.include_router(order_management.router, prefix="/order-management", tags=["order-management"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(procurement.router, prefix="/procurement", tags=["procurement"])
api_router.include_router(marketing.router, prefix="/marketing", tags=["marketing"])
api_router.include_router(forms.router, prefix="/forms-management", tags=["forms"])
api_router.include_router(complaints.router, prefix="/complaints-management", tags=["complaints"])
api_router.include_router(sla.router, prefix="/sla-management", tags=["sla"])
api_router.include_router(resources.router, prefix="/resource-management", tags=["resources"])
api_router.include_router(user_management.router, prefix="/user-management", tags=["user-management"])
api_router.include_router(integrations.logs.router, prefix="/integrations/logs", tags=["integrations"])
# Alias so /api/v1/integration-management/integration-logs/* works when requests hit backend directly (e.g. nginx)
api_router.include_router(integrations.logs.router, prefix="/integration-management/integration-logs", tags=["integrations"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(test_auth.router, tags=["test"])
api_router.include_router(external.router, prefix="/external", tags=["external"])
api_router.include_router(public.router, prefix="/public", tags=["public"])