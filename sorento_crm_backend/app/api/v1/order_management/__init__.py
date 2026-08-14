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
# `customers_select` FIRST. Both mount at `/customers`, and `customers.router` carries
# `GET /{customer_id}` - so mounted first it matches `/customers/select`, tries to read
# "select" as a customer id and answers 404 "Customer not found. Someone might have deleted
# it already." Every screen with a customer dropdown then shows that toast on load, which
# reads as a data problem rather than a routing one. FastAPI matches in registration order,
# so the literal path has to be registered before the parameterised one. Same defect family
# as the SLA `/integration/escalate` shadowing.
router.include_router(customers_select.router, prefix="/customers", tags=["customers"])
router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(order_statuses.router, prefix="/order-statuses", tags=["order-statuses"])