"""Order management API routes."""
from fastapi import APIRouter
from app.api.v1.order_management import (
    orders,
    customers,
    customers_select,
    order_statuses,
)

router = APIRouter()

router.include_router(orders.router, prefix="/orders", tags=["orders"])
# customers_select FIRST: it owns the literal /customers/select, and FastAPI matches in
# declaration order, so mounting it after customers.router made /{customer_id} capture
# the word "select" and 404 as "Customer not found". Guarded by
# tests/test_route_shadowing.py.
router.include_router(customers_select.router, prefix="/customers", tags=["customers"])
router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(order_statuses.router, prefix="/order-statuses", tags=["order-statuses"])