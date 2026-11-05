"""Sales orders (`/scm/sales-orders`), with their customer and agent.

The screen is `scm.dashboard.view` (`api/v1/scm/sales_orders.py`) and lists one document kind at a time, sales
orders by default (`SalesOrderService.list`: `doc_type`), so consignments stay out here too. The header holds no
money: the order total is summed from the lines in code (`sales_order_service._order_amount`), so no amount is
registered; sales are `billing_document.sales_amount` (AI-TOOLS-WAVE2).
"""
from __future__ import annotations

from app.models.order import DOC_TYPE_SALES_ORDER, SalesOrder
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _screen_rules(db) -> list:
    return [SalesOrder.doc_type == DOC_TYPE_SALES_ORDER]


register(
    EntityDef(
        key="sales_order",
        label="Sales orders",
        module="scm",
        model=SalesOrder,
        view_permission="scm.dashboard.view",
        fields={
            "so_number": FieldDef("SO number"),
            "order_date": FieldDef("Order date", note="The date the sales orders list filters on."),
            "debtor_code": FieldDef("Debtor code"),
            "debtor_name": FieldDef("Customer", note="The name the order was issued under."),
            "status": FieldDef("Status"),
            "priority": FieldDef("Priority"),
            "demand_class": FieldDef("Demand class", note="project, retail or empty (unclassified)."),
            "requested_delivery_date": FieldDef("Requested delivery date"),
            "po_ref": FieldDef("Customer PO ref."),
            "created_at": FieldDef("Created at", note="When the CRM received the order, not the order date."),
        },
        relations={"customer": ("customer", "customer_id"), "agent": ("sales_agent", "sales_agent_id")},
        name_by=("so_number", "debtor_name"),
        screen_path="/scm/sales-orders/{id}",
        pages=("/scm/sales-orders",),
        routes=("GET /api/v1/scm/sales-orders",),
        scope=_screen_rules,
    ),
)
