"""SCM purchase orders (`/scm/purchase-orders`), with their supplier.

The header carries no money: the screen's order total is summed from the lines, which are not registered yet.
"""
from __future__ import annotations

from app.models.procurement import PurchaseOrder, Supplier
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

register(
    EntityDef(
        key="supplier",
        label="Suppliers",
        # The module of the screen that shows it (the PO list), so a lookup is gated with its parent.
        module="scm",
        model=Supplier,
        view_permission=None,
        fields={"code": FieldDef("Supplier code", column="supplier_code"), "name": FieldDef("Supplier", column="supplier_name")},
    ),
    EntityDef(
        key="purchase_order",
        label="Purchase orders",
        module="scm",
        model=PurchaseOrder,
        view_permission="scm.dashboard.view",
        fields={
            "po_number": FieldDef("PO number"),
            "status": FieldDef("Status"),
            "issue_date": FieldDef("Order date"),
            "expected_date": FieldDef("Expected date"),
            "currency": FieldDef("Currency"),
            "created_at": FieldDef("Created at"),
        },
        relations={"supplier": ("supplier", "supplier_id")},
        name_by=("po_number",),
        screen_path="/scm/purchase-orders/{id}",
        pages=("/scm/purchase-orders",),
        routes=("GET /api/v1/scm/purchase-orders",),
    ),
)
