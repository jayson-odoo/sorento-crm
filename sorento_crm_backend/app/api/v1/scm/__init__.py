"""SCM (Supply Chain & Inventory Optimisation) API routes.

Mounted at ``/api/v1/scm`` behind ``require_module_enabled_with_api_key("scm")``.
Sub-routers: dashboard read-models, sales orders (CRUD + create-DO), purchase
orders (read-only at M1).
"""
from fastapi import APIRouter

from app.api.v1.scm import (
    analytics,
    config,
    coverage,
    dashboard,
    decisions,
    explainer,
    fulfilment,
    market,
    order_summary,
    plan_exceptions,
    outstanding_import,
    policies,
    purchase_history,
    purchase_orders,
    reorder_levels,
    reorder_runs,
    sales_orders,
    simulation,
)

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(config.router)
router.include_router(analytics.router)
router.include_router(policies.router)
router.include_router(reorder_levels.router)
router.include_router(reorder_runs.router)
router.include_router(sales_orders.router)
router.include_router(purchase_orders.router)
router.include_router(decisions.router)
router.include_router(outstanding_import.router)
router.include_router(explainer.router)
router.include_router(market.router)
router.include_router(coverage.router)
router.include_router(order_summary.router)
router.include_router(plan_exceptions.router)
router.include_router(purchase_history.router)
router.include_router(fulfilment.router)
router.include_router(simulation.router)
