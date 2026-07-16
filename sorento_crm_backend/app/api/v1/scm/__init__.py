"""SCM (Supply Chain & Inventory Optimisation) API routes.

Mounted at ``/api/v1/scm`` behind ``require_module_enabled_with_api_key("scm")``.
Sub-routers: dashboard read-models, sales orders (CRUD + create-DO), purchase
orders (read-only at M1).
"""
from fastapi import APIRouter

from app.api.v1.scm import (
    analytics,
    config,
    dashboard,
    decisions,
    explainer,
    market,
    policies,
    purchase_orders,
    reorder_runs,
    sales_orders,
)

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(config.router)
router.include_router(analytics.router)
router.include_router(policies.router)
router.include_router(reorder_runs.router)
router.include_router(sales_orders.router)
router.include_router(purchase_orders.router)
router.include_router(decisions.router)
router.include_router(explainer.router)
router.include_router(market.router)
