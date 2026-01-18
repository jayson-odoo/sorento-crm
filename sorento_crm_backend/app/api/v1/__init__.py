"""API v1 routes."""
from fastapi import APIRouter
from app.api.v1 import (
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
)

api_router = APIRouter()

# Include all module routers
api_router.include_router(master_data.router, prefix="/master-data", tags=["master-data"])
api_router.include_router(order_management.router, prefix="/order-management", tags=["order-management"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(procurement.router, prefix="/procurement", tags=["procurement"])
api_router.include_router(marketing.router, prefix="/marketing", tags=["marketing"])
api_router.include_router(forms.router, prefix="/forms-management", tags=["forms"])
api_router.include_router(complaints.router, prefix="/complaint-management", tags=["complaints"])
api_router.include_router(sla.router, prefix="/sla-management", tags=["sla"])
api_router.include_router(resources.router, prefix="/resource-management", tags=["resources"])
api_router.include_router(user_management.router, prefix="/user-management", tags=["user-management"])
api_router.include_router(integrations.logs.router, prefix="/integrations/logs", tags=["integrations"])
api_router.include_router(test_auth.router, tags=["test"])