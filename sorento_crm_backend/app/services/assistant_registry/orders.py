"""Delivery orders (`/order-management/orders`), with the customer and status they show."""
from __future__ import annotations

from app.models.order import Customer, Order, OrderStatus
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _not_deleted(db) -> list:
    # The list's own rule (`order_service.py`): a soft-deleted order is not on the screen.
    return [Order.deleted_at.is_(None)]


register(
    EntityDef(
        key="customer",
        label="Customers",
        module="order",
        model=Customer,
        view_permission=None,
        fields={"code": FieldDef("Customer code", column="customer_code"), "name": FieldDef("Customer name", column="customer_name")},
    ),
    EntityDef(
        key="order_status",
        label="Delivery order statuses",
        module="order",
        model=OrderStatus,
        view_permission=None,
        fields={"code": FieldDef("Status code", column="status_code"), "name": FieldDef("Status", column="status_name")},
    ),
    EntityDef(
        key="order",
        label="Delivery orders",
        module="order",
        model=Order,
        view_permission="order_management.orders.view",
        fields={
            "order_number": FieldDef("Order number"),
            "order_date": FieldDef("Order date"),
            "debtor_code": FieldDef("Debtor code"),
            "debtor_name": FieldDef("Debtor name"),
            "agent": FieldDef("Agent"),
            "salesman": FieldDef("Salesman"),
            "warehouse": FieldDef("Warehouse"),
            "branch_name": FieldDef("Branch"),
            "is_cancelled": FieldDef("Cancelled"),
            "subtotal_amount": FieldDef("Subtotal"),
            "total_amount": FieldDef("Total"),
            "estimated_delivery_date": FieldDef("Estimated delivery date"),
            "actual_delivery_date": FieldDef("Delivered on"),
            "created_at": FieldDef("Created at"),
        },
        relations={"customer": ("customer", "customer_id"), "status": ("order_status", "order_status_id")},
        screen_path="/order-management/orders/{id}",
        pages=("/order-management",),
        routes=("GET /api/v1/order-management/orders/",),
        scope=_not_deleted,
    ),
)
