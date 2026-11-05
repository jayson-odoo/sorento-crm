"""Delivery orders (`/order-management/orders`), with the customer and status they show."""
from __future__ import annotations

from app.models.order import Customer, Order, OrderStatus
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _screen_rules(db) -> list:
    """The list's own rules (`order_service.py`): a soft-deleted order is not on the screen, and a brand-scoped
    contact sees only orders with a line of one of its brands (`scope_product_filter`)."""
    from sqlalchemy import select

    from app.models.base import get_brand_scope
    from app.models.order import OrderLine
    from app.services.order_service import scope_product_filter

    clauses = [Order.deleted_at.is_(None)]
    if get_brand_scope(db):
        in_scope = select(OrderLine.order_id).where(OrderLine.product_id.in_(scope_product_filter(db, None)))
        clauses.append(Order.id.in_(in_scope))
    return clauses


register(
    # The Customers list (`/order-management/customers`, menu slug `order_management.customers.view`; company scope
    # only, no own rule). Also the lookup behind every document's `customer` relation. Phone, email, address and
    # the AR figures are left out (AI-TOOLS-WAVE2).
    EntityDef(
        key="customer",
        label="Customers",
        module="order",
        model=Customer,
        view_permission="order_management.customers.view",
        fields={
            "code": FieldDef("Customer code", column="customer_code"),
            "name": FieldDef("Customer name", column="customer_name"),
            "is_active": FieldDef("Active"),
            "region": FieldDef("Region"),
            "debtor_type": FieldDef("Debtor type", column="autocount_debtor_type"),
            "created_at": FieldDef("Created at"),
        },
        relations={"agent": ("sales_agent", "sales_agent_id")},
        name_by=("code", "name"),
        # "Active customers": the Customers list's own Active filter (`order_service._build_customer_list_query`,
        # `status=active` is `is_active`), applied unless the query names `is_active` (crew pass, 5 Nov).
        default_filters=(("is_active", "eq", True, "Inactive customers excluded."),),
        hint="customers; agent.code for an agent's customers",
        screen_path="/order-management/customers/{id}",
        pages=("/order-management/customers",),
        routes=("GET /api/v1/order-management/customers/",),
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
            "order_date": FieldDef(
                "Order date", note="The Order date the Delivery Orders list filters on; use it for a period such as last month.",
            ),
            "debtor_code": FieldDef("Debtor code"),
            "debtor_name": FieldDef("Debtor name"),
            "agent": FieldDef(
                "Agent", note="The Agent column of the Delivery Orders list; group by this for per agent questions.",
            ),
            "salesman": FieldDef(
                "Salesman", note="The salesman on the order's detail page, not the list's Agent column.",
            ),
            "warehouse": FieldDef("Warehouse"),
            "branch_name": FieldDef("Branch"),
            "is_cancelled": FieldDef("Cancelled"),
            "subtotal_amount": FieldDef("Subtotal", whole_document=True),
            "total_amount": FieldDef("Total", whole_document=True),
            "estimated_delivery_date": FieldDef("Estimated delivery date"),
            "actual_delivery_date": FieldDef("Delivered on"),
            "created_at": FieldDef("Created at", note="When the CRM received the order, not the order date."),
        },
        relations={"customer": ("customer", "customer_id"), "status": ("order_status", "order_status_id")},
        name_by=("order_number", "debtor_name"),
        # Owner ruling (5 Nov): an order count or total is of orders that are not cancelled, and says so.
        default_filters=((
            "is_cancelled", "eq", False,
            "Cancelled orders excluded.",
        ),),
        screen_path="/order-management/orders/{id}",
        pages=("/order-management",),
        routes=("GET /api/v1/order-management/orders/",),
        hint="delivery orders (DO); per agent = group by agent, period = order_date",
        scope=_screen_rules,
    ),
)
