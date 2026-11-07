"""Stock balances (`/inventory-management/stock`), with the warehouse lookup (AI-TOOLS-WAVE3).

The screen is `GET /api/v1/inventory/stock/balance` on `inventory.stock.view` (`api/v1/inventory/stock.py`), module
`inventory`. A staff member's rows are every stock row of their company in an active warehouse
(`inventory_service.list_stock`: `Stock.warehouse.has(Warehouse.is_active)`), zero rows included; the status is the
grid's own (`Stock.status`, read in SQL by `inventory_service.stock_status_expr`).

Staff panel only (`EntityDef.panel_only`): a contact's stock answer carries the stock-visibility policy, the sellable
grant and the stock switch, which live in `crm_inventory_stock_balance_list` alone.
"""
from __future__ import annotations

from app.models.inventory import Stock, Warehouse
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

STOCK_VIEW = "inventory.stock.view"


def _status():
    from app.services.inventory_service import stock_status_expr

    return stock_status_expr()


def _reorder_level():
    from sqlalchemy import select

    from app.models.product import Product

    return select(Product.reorder_level).where(Product.id == Stock.product_id).correlate(Stock).scalar_subquery()


def _screen_rules(db, user_id: str | None = None) -> list:
    """The stock list's own rule (`inventory_service.py` `list_stock`): rows of active warehouses only."""
    from sqlalchemy import select

    return [Stock.warehouse_id.in_(select(Warehouse.id).where(Warehouse.is_active.is_(True)))]


register(
    EntityDef(
        key="warehouse",
        label="Warehouses",
        module="inventory",
        model=Warehouse,
        view_permission=None,
        fields={
            "code": FieldDef("Warehouse code", column="warehouse_code"),
            "name": FieldDef("Warehouse", column="warehouse_name"),
            "location": FieldDef("Location"),
        },
        name_by=("code", "name"),
    ),
    EntityDef(
        key="stock",
        label="Stock balances",
        module="inventory",
        model=Stock,
        view_permission=STOCK_VIEW,
        fields={
            "quantity_on_hand": FieldDef("Quantity", note="On hand in that warehouse."),
            "quantity_reserved": FieldDef("Reserved"),
            "quantity_available": FieldDef("Available", note="On hand minus reserved; the figure status reads."),
            "quantity_damaged": FieldDef("Damaged"),
            "reorder_level": FieldDef("Reorder level", expr=_reorder_level, note="The product's reorder level."),
            "status": FieldDef(
                "Status", expr=_status,
                note="critical (nothing available), low (under the reorder level), overstock (over twice it) or "
                     "normal, as the stock screen shows it. Low stock = status in [low, critical].",
            ),
            "last_count_date": FieldDef("Last counted"),
        },
        relations={"product": ("product", "product_id"), "warehouse": ("warehouse", "warehouse_id")},
        list_fields=("product.product_code", "warehouse.code", "quantity_available", "status"),
        pages=("/inventory-management/stock",),
        routes=("GET /api/v1/inventory/stock/balance",),
        scope=_screen_rules,
        panel_only=(
            "Stock is not read with crm_query on this channel: use crm_inventory_stock_balance_list, which applies "
            "this contact's stock visibility."
        ),
        hint="stock per product and warehouse (on hand, reserved, available, status critical|low|normal|overstock); "
             "low stock = status in [low, critical]; total stock = sum quantity_available",
    ),
)
