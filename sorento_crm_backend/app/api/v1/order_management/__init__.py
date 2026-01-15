"""Order management API routes."""
from fastapi import APIRouter
from app.api.v1.order_management import orders, customers, customers_select, order_statuses, order_statuses_select

router = APIRouter()

router.include_router(orders.router, prefix="/orders", tags=["orders"])
router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(customers_select.router, prefix="/customers", tags=["customers"])
router.include_router(order_statuses.router, prefix="/order-statuses", tags=["order-statuses"])
router.include_router(order_statuses_select.router, prefix="/order-statuses", tags=["order-statuses"])